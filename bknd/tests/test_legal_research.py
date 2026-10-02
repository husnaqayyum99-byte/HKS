import json
from unittest.mock import Mock
from unittest.mock import patch

from app.agents import followup_agent, intake_agent, orchestrator, research_agent, response_agent
from app.agents.orchestrator import process_case
from app.api.conversations import format_case_response
from app.legal_sources.source_registry import LegalSource, get_relevant_sources
from app.legal_sources import evidence_retriever
from app.legal_sources.statute_retriever import (
    LawRecord,
    _record_matches,
    _section_references,
)
from app.agents.verification_agent import verify_claim
from app.legal_sources.evidence import EvidenceItem
from app.agents.research_agent import EvidenceGapPlan
from app.api.legal import normalize_analysis


class Model:
    def __init__(self, data):
        self.data = data

    def model_dump(self):
        return self.data


def test_pakistan_criminal_cases_select_federal_legislation():
    sources = get_relevant_sources("Pakistan", "criminal")

    assert any(source.name == "Pakistan Code" for source in sources)


def test_statute_matching_respects_jurisdiction_and_act_title():
    federal_record = LawRecord(
        "Pakistan Penal Code (PPC), 1860",
        "https://pakistancode.gov.pk/english/law",
        "Federal",
        "pakistancode.gov.pk",
    )
    provincial_record = LawRecord(
        "The Khyber Pakhtunkhwa Police Act, 2017",
        "https://kpcode.kp.gov.pk/homepage/lawDetails/1",
        "Khyber Pakhtunkhwa",
        "kpcode.kp.gov.pk",
    )

    assert _record_matches(federal_record, "Pakistan Penal Code")
    assert _record_matches(provincial_record, "Khyber Pakhtunkhwa Police Act")
    assert not _record_matches(federal_record, "Khyber Pakhtunkhwa Police Act")
    assert _record_matches(federal_record, "Pakistan Penal Code, 1860")
    old_motor_vehicles_act = LawRecord(
        "Motor Vehicles Act, 1939",
        "https://pakistancode.gov.pk/english/old-act",
        "Federal",
        "pakistancode.gov.pk",
    )
    assert not _record_matches(old_motor_vehicles_act, "Motor Vehicles Act, 1999")


def test_official_source_link_discovery_accepts_registered_subdomains(monkeypatch):
    source = LegalSource(
        name="NADRA",
        authority="National Database and Registration Authority",
        jurisdiction="Pakistan",
        source_type="government_authority",
        domain="Identity documents and registration services",
        official_domain="nadra.gov.pk",
    )
    response = Mock()
    response.text = '<a href="https://www.nadra.gov.pk/lost-cnic-replacement">Lost CNIC replacement procedure</a><a href="https://fake-nadra.gov.pk/lost-cnic">Other</a>'
    response.url = "https://www.nadra.gov.pk/"
    monkeypatch.setattr(evidence_retriever.requests, "get", lambda *_args, **_kwargs: response)

    links = evidence_retriever.find_relevant_links(source, "lost CNIC replacement procedure")

    assert links == ["https://www.nadra.gov.pk/lost-cnic-replacement"]


def test_verifier_citations_are_mapped_to_retrieved_sources():
    source = EvidenceItem(
        source_name="Pakistan Code",
        source_url="https://pakistancode.gov.pk/law.pdf",
        source_title="Code of Criminal Procedure",
        jurisdiction="Federal",
        source_type="legislation",
        relevant_text="Information in cognizable cases",
        citation="CrPC section 154",
    )
    model_response = {
        "claim": "FIR procedure",
        "supported": True,
        "confidence": "high",
        "reasoning": "The retrieved provision addresses cognizable cases.",
        "evidence_used": ["Code of Criminal Procedure, CrPC section 154"],
        "uncertainty": [],
    }

    with patch(
        "app.agents.verification_agent.generate_response",
        return_value=json.dumps(model_response),
    ):
        result = verify_claim("FIR procedure", [source])

    assert result.evidence_used == [source]


def test_section_references_select_theft_and_fir_provisions():
    page_text = """138. Procedure where he claims jury
149. Police to prevent cognizable offences
154. Information in cognizable cases
364A. Kidnapping or abducting a person under fourteen
378. Theft
379. Punishment for theft
"""

    references = _section_references(
        page_text,
        ["reporting a cognizable theft to police and FIR procedure", "theft of a motorcycle"],
    )

    assert any(reference.startswith("section 154") for reference in references)
    assert any(reference.startswith("section 378") for reference in references)
    assert not any(reference.startswith("section 138") for reference in references)
    assert not any(reference.startswith("section 364A") for reference in references)


def test_chat_response_displays_law_citation_and_review_status():
    text = format_case_response({
        "intake": {"problem_summary": "A motorcycle was stolen."},
        "response": {
            "answer": "The relevant theft provision is identified below.",
            "next_steps": ["File a police report."],
            "documents_needed": [],
            "uncertainty": [],
            "disclaimer": "",
        },
        "evidence": [{
            "source_type": "legislation",
            "citation": "Pakistan Penal Code, section 378 (Theft), page 68",
            "source_url": "https://pakistancode.gov.pk/pdffiles/example.pdf",
            "official_status": "Under Review",
        }],
    })

    assert "Your to-do list:" in text
    assert "section 378" in text
    assert "https://pakistancode.gov.pk/pdffiles/example.pdf" in text
    assert "under review" in text.lower()


def test_chat_response_uses_localized_labels():
    labels = {
        "caseSummary": "Muamlay ka khulasa",
        "currentGuidance": "Filhal hum yeh bata sakte hain",
        "nextSteps": "Aap ke aglay qadam",
        "needDescription": "Mukhtasaran batayein kya hua.",
    }
    text = format_case_response({
        "intake": {"problem_summary": "Maslay ka khulasa"},
        "response": {
            "answer": "Roman Urdu mein jawab.",
            "next_steps": ["Mutaliqa daftar se rabta karein."],
            "documents_needed": [],
            "uncertainty": [],
            "disclaimer": "",
        },
        "evidence": [],
    }, labels)

    assert "Muamlay ka khulasa:" in text
    assert "Filhal hum yeh bata sakte hain:" in text
    assert "Aap ke aglay qadam:" in text
    assert "Case summary:" not in text
    assert format_case_response({"status": "needs_description"}, labels) == "Mukhtasaran batayein kya hua."


def test_chat_clarification_response_shows_questions_without_guidance():
    text = format_case_response({
        "status": "needs_clarification",
        "intake": {"problem_summary": "An employment concern."},
        "follow_up": {"questions": ["When were the wages due?"]},
        "response": {},
    })

    assert "When were the wages due?" in text
    assert "Case summary:" in text
    assert "What we can tell you now" not in text


def test_evidence_unavailable_chat_preserves_questions_and_safe_step():
    text = format_case_response({
        "status": "evidence_unavailable",
        "intake": {"problem_summary": "An employment concern."},
        "follow_up": {"questions": ["Which city did this happen in?"]},
        "evidence": [],
    })

    assert "Which city did this happen in?" in text
    assert "Keep relevant messages, documents, photos, and dates together." in text
    assert "No official source evidence was retrieved" in text


def test_roman_urdu_analysis_fallback_uses_roman_urdu_time_units():
    result = normalize_analysis({}, "A property issue", "Punjab", "roman_urdu")

    assert [step["time"] for step in result["timeline"]] == [
        "1 se 3 din",
        "1 se 2 haftay",
        "1 se 3 mahinay",
    ]


def test_chat_agents_request_natural_roman_urdu(monkeypatch):
    prompts = []

    def fake_response(prompt):
        prompts.append(prompt)
        return "{}"

    monkeypatch.setattr(intake_agent, "generate_response", fake_response)
    monkeypatch.setattr(followup_agent, "generate_response", fake_response)
    monkeypatch.setattr(response_agent, "generate_response", fake_response)

    intake_agent.intake_case("Mera masla", language="roman_urdu")
    followup_agent.generate_follow_up_questions(
        user_message="Mera masla",
        intake_data={},
        classification_data={},
        language="roman_urdu",
    )
    response_agent.generate_final_response(
        user_message="Mera masla",
        intake_data={},
        classification_data={},
        evidence=[],
        verification_results=[],
        language="roman_urdu",
    )

    assert len(prompts) == 3
    assert all("natural Pakistani Roman Urdu using Latin letters only" in prompt for prompt in prompts)
    assert all("Do not use Urdu script" in prompt for prompt in prompts)


def test_final_response_prompt_connects_user_facts_to_retrieved_law(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        response_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or json.dumps({"answer": "Explanation."}),
    )

    response_agent.generate_final_response(
        user_message="My landlord changed the locks while my belongings were inside.",
        intake_data={"problem_summary": "A tenant was locked out of a rented home."},
        classification_data={"jurisdiction": "Pakistan"},
        evidence=[],
        verification_results=[],
    )

    assert "Begin the answer by briefly restating the user's situation" in prompts[0]
    assert "connect its verified rule to the stated facts" in prompts[0]
    assert "say what is uncertain and what information is needed" in prompts[0]
    assert "A source's silence does not establish that a requirement is absent" in prompts[0]
    assert "Never state that a procedure is not required" in prompts[0]
    assert "evidence affirmatively establishes that conclusion" in prompts[0]


def test_gap_agent_targets_unanswered_parts_and_rejects_silence_inference(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        "app.agents.research_agent.generate_response",
        lambda prompt: prompts.append(prompt) or json.dumps({
            "research_questions": ["What official documents are required for replacement?"],
            "laws_to_check": [],
        }),
    )
    evidence = [EvidenceItem(
        source_name="Pakistan Code",
        source_url="https://pakistancode.gov.pk/ordinance.pdf",
        source_title="NADRA Ordinance",
        jurisdiction="Federal",
        source_type="legislation",
        relevant_text="Report the loss to a Registration Officer.",
        citation="NADRA Ordinance, section 30",
    )]

    result = research_agent.identify_evidence_gaps(
        user_message="Do I need an FIR and what documents do I need?",
        intake_data={},
        classification_data={},
        research_plan={"research_questions": ["What happens after loss?"], "laws_to_check": []},
        evidence=evidence,
    )

    assert result.research_questions == ["What official documents are required for replacement?"]
    assert "A source's silence is not evidence" in prompts[0]
    assert "Report the loss to a Registration Officer." in prompts[0]


def test_greeting_gets_short_case_description_prompt():
    assert process_case("hi") == {"status": "needs_description"}
    assert "describe what happened" in format_case_response({"status": "needs_description"})


def test_pipeline_returns_clarification_before_research(monkeypatch):
    intake = Model({"problem_summary": "A contract was signed.", "facts": []})
    classification = Model({
        "legal_domain": "civil",
        "matter_type": "contract",
        "jurisdiction": "Pakistan",
        "locality": "unknown",
    })
    follow_up = Model({
        "needs_follow_up": True,
        "questions": ["What outcome are you seeking?"],
        "reason": "The requested outcome is unknown.",
    })
    research = Mock(side_effect=AssertionError("research should wait for clarification"))
    evidence = Mock(side_effect=AssertionError("evidence retrieval should wait for clarification"))

    monkeypatch.setattr(orchestrator, "intake_case", lambda *_args, **_kwargs: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_kwargs: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", research)
    monkeypatch.setattr(orchestrator, "collect_evidence", evidence)

    result = process_case("I signed a contract.")

    assert result["status"] == "needs_clarification"
    assert result["follow_up"]["questions"] == ["What outcome are you seeking?"]
    research.assert_not_called()
    evidence.assert_not_called()


def test_pipeline_uses_research_plan_laws_for_any_domain(monkeypatch):
    intake = Model({"problem_summary": "My employer withheld wages.", "facts": []})
    intake.problem_summary = "My employer withheld wages."
    intake.category = "employment"
    intake.facts = []
    classification = Model({
        "legal_domain": "employment",
        "matter_type": "unpaid wages",
        "jurisdiction": "Punjab",
        "locality": "Lahore",
    })
    classification.legal_domain = "employment"
    classification.matter_type = "unpaid wages"
    classification.jurisdiction = "Punjab"
    classification.locality = "Lahore"
    follow_up = Model({"needs_follow_up": False, "questions": [], "reason": ""})
    research = Model({
        "research_questions": ["Minimum wage and wage recovery procedure"],
        "evidence_needed": [],
        "laws_to_check": ["Punjab Payment of Wages Act"],
    })
    research.research_questions = research.data["research_questions"]
    research.evidence_needed = research.data["evidence_needed"]
    research.laws_to_check = research.data["laws_to_check"]
    final = Model({"answer": "Sourced answer."})
    statute_lookup = Mock(return_value=[])
    evidence_lookup = Mock(return_value=[])

    monkeypatch.setattr(orchestrator, "intake_case", lambda _, **__: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda _: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", lambda *_: research)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: EvidenceGapPlan())
    monkeypatch.setattr(orchestrator, "get_relevant_sources", lambda *_: [])
    monkeypatch.setattr(orchestrator, "collect_evidence", evidence_lookup)
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", statute_lookup)
    monkeypatch.setattr(orchestrator, "verify_claim", lambda claim, _: Model({"claim": claim}))
    monkeypatch.setattr(orchestrator, "generate_final_response", lambda **_: final)

    result = process_case("My employer withheld wages.")

    assert result["status"] == "evidence_unavailable"
    assert statute_lookup.call_args.args[0] == ["Punjab Payment of Wages Act"]
    assert statute_lookup.call_args.args[1] == ["Minimum wage and wage recovery procedure"]
    evidence_lookup.assert_called_once()


def test_pipeline_retrieves_evidence_for_gaps_before_final_response(monkeypatch):
    intake = Model({"problem_summary": "A lost CNIC replacement.", "facts": []})
    classification = Model({
        "legal_domain": "identity documents",
        "matter_type": "lost CNIC",
        "jurisdiction": "Pakistan",
        "locality": "Chitral",
    })
    classification.legal_domain = "identity documents"
    classification.jurisdiction = "Pakistan"
    classification.locality = "Chitral"
    follow_up = Model({"needs_follow_up": False, "questions": [], "reason": ""})
    research = Model({
        "research_questions": ["What must a person do after losing a CNIC?"],
        "evidence_needed": [],
        "laws_to_check": ["National Database and Registration Authority Ordinance, 2000"],
    })
    research.research_questions = research.data["research_questions"]
    research.laws_to_check = research.data["laws_to_check"]
    gap_plan = Model({
        "research_questions": [
            "Is a police report or FIR required to replace a lost CNIC?",
            "What official documents and procedure are required to replace a lost CNIC?",
        ],
        "laws_to_check": [],
    })
    gap_plan.research_questions = gap_plan.data["research_questions"]
    gap_plan.laws_to_check = gap_plan.data["laws_to_check"]
    official_source = LegalSource(
        name="NADRA",
        authority="National Database and Registration Authority",
        jurisdiction="Pakistan",
        source_type="government_authority",
        domain="Identity documents and registration services",
        official_domain="nadra.gov.pk",
    )
    initial_evidence = EvidenceItem(
        source_name="Pakistan Code",
        source_url="https://pakistancode.gov.pk/ordinance.pdf",
        source_title="NADRA Ordinance, 2000",
        jurisdiction="Federal",
        source_type="legislation",
        relevant_text="A person must report the loss to a Registration Officer.",
        citation="NADRA Ordinance, 2000, section 30",
    )
    supplemental_evidence = EvidenceItem(
        source_name="NADRA",
        source_url="https://www.nadra.gov.pk/lost-id-card",
        source_title="Lost identity card procedure",
        jurisdiction="Pakistan",
        source_type="government_authority",
        relevant_text="Official replacement procedure and required documents.",
    )
    retrieval_queries = []
    response_evidence = []

    def collect_general_evidence(_sources, questions):
        retrieval_queries.append(list(questions))
        if len(retrieval_queries) == 1:
            return [initial_evidence]
        return [supplemental_evidence]

    monkeypatch.setattr(orchestrator, "intake_case", lambda *_args, **_kwargs: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_kwargs: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", lambda *_args: research)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: gap_plan, raising=False)
    monkeypatch.setattr(orchestrator, "get_relevant_sources", lambda *_args: [official_source])
    monkeypatch.setattr(orchestrator, "collect_evidence", collect_general_evidence)
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", lambda *_args: [])
    monkeypatch.setattr(
        orchestrator,
        "verify_claim",
        lambda claim, available: Model({"claim": claim, "evidence_used": [item.model_dump() for item in available]}),
    )
    monkeypatch.setattr(
        orchestrator,
        "generate_final_response",
        lambda **kwargs: response_evidence.extend(kwargs["evidence"]) or Model({"answer": "Evidence reviewed."}),
    )

    result = process_case("I lost my CNIC yesterday. Do I need an FIR and what documents do I need?")

    assert len(retrieval_queries) == 2
    assert retrieval_queries[1] == gap_plan.research_questions
    assert result["status"] == "completed"
    assert supplemental_evidence in [item for item in response_evidence]
    assert len(response_evidence) == 2


def test_pipeline_continues_after_user_answers_clarification(monkeypatch):
    intake = Model({"problem_summary": "An employment concern.", "facts": []})
    classification = Model({
        "legal_domain": "employment",
        "matter_type": "unpaid wages",
        "jurisdiction": "Punjab",
        "locality": "Lahore",
    })
    classification.legal_domain = "employment"
    classification.jurisdiction = "Punjab"
    classification.locality = "Lahore"
    follow_up = Model({"needs_follow_up": False, "questions": [], "reason": ""})
    research = Model({"research_questions": ["Wage recovery process"], "evidence_needed": [], "laws_to_check": []})
    research.research_questions = research.data["research_questions"]
    research.laws_to_check = research.data["laws_to_check"]
    research_call = Mock(return_value=research)

    monkeypatch.setattr(orchestrator, "intake_case", lambda *_args, **_kwargs: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_kwargs: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", research_call)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: EvidenceGapPlan())
    monkeypatch.setattr(orchestrator, "get_relevant_sources", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "collect_evidence", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", lambda *_args: [])

    result = process_case(
        "The wages were due last week.",
        conversation_history=[
            {"role": "assistant", "content": "When were the wages due?"},
            {"role": "user", "content": "The wages were due last week."},
        ],
    )

    assert result["status"] == "evidence_unavailable"
    research_call.assert_called_once()


def test_pipeline_completes_when_evidence_is_available(monkeypatch):
    intake = Model({"problem_summary": "A tenant received a written notice.", "facts": []})
    classification = Model({
        "legal_domain": "housing",
        "matter_type": "tenancy",
        "jurisdiction": "Pakistan",
        "locality": "unknown",
    })
    classification.legal_domain = "housing"
    classification.jurisdiction = "Pakistan"
    classification.locality = "unknown"
    follow_up = Model({"needs_follow_up": False, "questions": [], "reason": ""})
    research = Model({"research_questions": ["What does the official tenancy law say about notice?"], "evidence_needed": [], "laws_to_check": []})
    research.research_questions = research.data["research_questions"]
    research.laws_to_check = research.data["laws_to_check"]
    evidence_item = EvidenceItem(
        source_name="Pakistan Code",
        source_url="https://pakistancode.gov.pk/tenancy.pdf",
        source_title="Tenancy law",
        jurisdiction="Federal",
        source_type="legislation",
        relevant_text="Official tenancy provision.",
        citation="Tenancy law",
    )
    final = Model({"answer": "The retrieved source addresses notice requirements."})

    monkeypatch.setattr(orchestrator, "intake_case", lambda *_args, **_kwargs: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_kwargs: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", lambda *_args: research)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: EvidenceGapPlan())
    monkeypatch.setattr(orchestrator, "get_relevant_sources", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "collect_evidence", lambda *_args: [evidence_item])
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "verify_claim", lambda claim, _evidence: Model({"claim": claim}))
    monkeypatch.setattr(orchestrator, "generate_final_response", lambda **_kwargs: final)

    result = process_case("A tenant received a written notice.")

    assert result["status"] == "completed"
    assert result["response"]["answer"] == "The retrieved source addresses notice requirements."
    assert result["evidence"][0]["citation"] == "Tenancy law"