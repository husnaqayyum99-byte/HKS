import json
from dataclasses import replace
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from app.agents import classification_agent, followup_agent, intake_agent, orchestrator, research_agent, response_agent
from app.agents.orchestrator import process_case
from app.api.conversations import format_case_response
from app.legal_sources.source_registry import LegalSource, get_relevant_sources
from app.legal_sources.domain_catalog import law_search_candidates
from app.legal_sources import evidence_retriever
from app.legal_sources import source_registry
from app.legal_sources import source_health
from app.legal_sources.statute_retriever import (
    LawRecord,
    find_law_records,
    _record_matches,
    _section_references,
)
from app.agents.verification_agent import verify_claim
from app.agents import verification_agent
from app.legal_sources.evidence import EvidenceItem
from app.agents.research_agent import EvidenceGapPlan


class Model:
    def __init__(self, data):
        self.data = data

    def model_dump(self):
        return self.data


def test_pakistan_property_cases_select_relevant_federal_legislation():
    sources = get_relevant_sources("Pakistan", "property")

    assert any(source.name == "Pakistan Code" for source in sources)
    assert sources[0].jurisdiction == "Federal"


def test_curated_sources_match_chitral_topics_and_expose_catalog_metadata():
    sources = get_relevant_sources("Khyber Pakhtunkhwa", "property", "Chitral")

    assert any(source.name == "Khyber Pakhtunkhwa Code" for source in sources)
    assert any(source.name == "Pakistan Code" for source in sources)
    revenue = next(source for source in sources if source.name == "Khyber Pakhtunkhwa Revenue and Estate Department")
    assert revenue.authority == "Revenue and Estate Department, Government of Khyber Pakhtunkhwa"
    assert revenue.official_domain == "revenue.kp.gov.pk"
    assert revenue.search_url == "https://revenue.kp.gov.pk/"
    assert "land administration" in revenue.information_types
    assert "inheritance" in revenue.legal_topics
    assert all(source.active for source in sources)
    first_federal = next(
        index for index, source in enumerate(sources)
        if source.jurisdiction == "Federal"
    )
    assert all(
        source.jurisdiction == "Khyber Pakhtunkhwa"
        for source in sources[:first_federal]
    )


def test_locality_does_not_infer_or_override_unknown_jurisdiction():
    assert get_relevant_sources("Unknown", "property", "Chitral") == []
    assert get_relevant_sources("Punjab", "property", "Lahore") == []


def test_kp_selection_prioritizes_kp_and_retains_relevant_federal_sources():
    sources = get_relevant_sources(
        "Khyber Pakhtunkhwa",
        "property",
        priority_jurisdictions=["Federal", "Khyber Pakhtunkhwa"],
    )

    assert sources[0].jurisdiction == "Khyber Pakhtunkhwa"
    assert any(source.name == "Pakistan Code" for source in sources)
    assert all(source.jurisdiction in {"Khyber Pakhtunkhwa", "Federal", "Pakistan"} for source in sources)
    kp_priorities = [
        source.priority for source in sources
        if source.jurisdiction == "Khyber Pakhtunkhwa"
    ]
    assert kp_priorities == sorted(kp_priorities, reverse=True)


def test_research_source_type_preference_orders_matching_authority():
    sources = get_relevant_sources(
        "Khyber Pakhtunkhwa",
        "property",
        source_types=["revenue department"],
    )

    assert sources[0].name == "Khyber Pakhtunkhwa Revenue and Estate Department"


def test_research_jurisdiction_preference_orders_only_eligible_sources():
    sources = get_relevant_sources(
        "Pakistan",
        "identity documents",
        priority_jurisdictions=["Pakistan", "Federal"],
    )

    assert sources[0].name == "NADRA"
    assert all(source.jurisdiction in {"Federal", "Pakistan"} for source in sources)


def test_unrelated_legislation_does_not_match_by_source_type_alone():
    assert get_relevant_sources("Pakistan", "traffic") == []


def test_information_type_can_match_research_domain():
    sources = get_relevant_sources("Khyber Pakhtunkhwa", "land administration")

    assert sources[0].name == "Khyber Pakhtunkhwa Revenue and Estate Department"


def test_user_facts_relevance_can_prioritize_the_matching_registered_source():
    sources = get_relevant_sources(
        "Khyber Pakhtunkhwa",
        "property",
        research_context="Agricultural land inherited by three heirs",
    )

    assert sources[0].name == "Khyber Pakhtunkhwa Revenue and Estate Department"


def test_registered_sources_cover_supported_domains_without_cross_jurisdiction_leaks():
    cases = [
        ("Pakistan", "identity_documents", "NADRA"),
        ("Khyber Pakhtunkhwa", "family_marriage", "Khyber Pakhtunkhwa Code"),
        ("Khyber Pakhtunkhwa", "child_protection", "Khyber Pakhtunkhwa Code"),
        ("Khyber Pakhtunkhwa", "harassment_protection", "Khyber Pakhtunkhwa Code"),
        ("Pakistan", "fraud_cybercrime", "Pakistan Code"),
        ("Khyber Pakhtunkhwa", "land_revenue", "Khyber Pakhtunkhwa Revenue and Estate Department"),
        ("Khyber Pakhtunkhwa", "inheritance_succession", "Khyber Pakhtunkhwa Code"),
        ("Khyber Pakhtunkhwa", "traffic_accident", "Khyber Pakhtunkhwa Code"),
        ("Khyber Pakhtunkhwa", "traffic_services", "Peshawar Traffic Police Services"),
        ("Khyber Pakhtunkhwa", "police_reporting", "KP Police Complaint Portal"),
    ]

    for jurisdiction, domain, expected_source in cases:
        sources = get_relevant_sources(jurisdiction, domain)
        assert any(source.name == expected_source for source in sources), (domain, sources)
        assert all(source.active and source.search_url.startswith("https://") for source in sources)

    assert get_relevant_sources("Khyber Pakhtunkhwa", "domicile_verification") == []
    assert get_relevant_sources("Unknown", "identity_documents") == []


def test_confirmed_direct_official_service_targets_are_registered():
    by_name = {source.name: source for source in source_registry.LEGAL_SOURCES}

    assert by_name["NADRA"].search_url == "https://www.nadra.gov.pk/"
    assert by_name["NADRA CNIC Services"].search_url == (
        "https://www.nadra.gov.pk/identityDocument/cnic?tab=nic&action=new"
    )
    assert by_name["KP Revenue Online Services"].search_url == "https://revenue.kp.gov.pk/services/"
    assert by_name["KP Land Records Service Centers"].search_url == "https://kplr.gkp.pk/SDCCenters"
    assert by_name["KP Police Complaint Portal"].search_url == (
        "https://complaints.kppolice.gov.pk/register-complaint"
    )


def test_classification_keeps_fine_grained_legal_subtype(monkeypatch):
    monkeypatch.setattr(
        classification_agent,
        "generate_response",
        lambda _prompt: json.dumps({
            "legal_domain": "harassment_protection",
            "legal_subtype": "domestic_violence",
            "jurisdiction": "Khyber Pakhtunkhwa",
            "locality": "Chitral",
            "matter_type": "protection navigation",
            "requires_local_procedure": True,
            "confidence": "high",
        }),
    )

    result = classification_agent.classify_case({"problem_summary": "A partner is threatening me at home."})

    assert result.legal_domain == "harassment_protection"
    assert result.legal_subtype == "domestic_violence"


def test_classification_prompt_prevents_collapsing_fraud_harassment_and_accidents(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        classification_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or json.dumps({}),
    )

    result = classification_agent.classify_case({"problem_summary": "A person says fraud happened."})

    prompt = prompts[0]
    assert result.legal_domain == "unclear"
    assert "Fraud is not automatically cybercrime" in prompt
    assert "Harassment depends on context" in prompt
    assert "Distinguish road accidents" in prompt
    assert "A reported incident is not proof that a crime occurred" in prompt


def test_intake_preserves_structured_road_incident_fields(monkeypatch):
    payload = {
        "problem_summary": "A car was damaged in a road accident.",
        "category": "traffic_accident",
        "location": "Chitral",
        "facts": ["The other driver disputes responsibility."],
        "missing_information": [],
        "urgency": "normal",
        "incident_location": "Chitral",
        "incident_type": "road accident",
        "vehicle_damage": "car body damage",
        "responsibility_dispute": True,
        "compensation_dispute": True,
    }
    monkeypatch.setattr(intake_agent, "generate_response", lambda _prompt: json.dumps(payload))

    result = intake_agent.intake_case("My car was damaged in Chitral.")

    assert result.incident_location == "Chitral"
    assert result.incident_type == "road accident"
    assert result.vehicle_damage == "car body damage"
    assert result.responsibility_dispute is True
    assert result.compensation_dispute is True


def test_law_candidates_follow_explicit_subtypes_and_jurisdiction():
    assert law_search_candidates({
        "legal_subtype": "online_harassment",
        "jurisdiction": "Pakistan",
    }) == ["Prevention of Electronic Crimes Act, 2016"]
    assert law_search_candidates({
        "legal_subtype": "offline_fraud",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == []
    assert law_search_candidates({
        "legal_subtype": "general_harassment_complaint",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == []
    assert law_search_candidates({
        "legal_subtype": "workplace_harassment",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == ["Protection Against Harassment of Women at the Workplace Act, 2010"]
    assert law_search_candidates({
        "legal_subtype": "domestic_violence",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == ["Khyber Pakhtunkhwa Domestic Violence Against Women Prevention and Protection Act, 2021"]
    assert law_search_candidates({
        "legal_subtype": "child_labour",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == ["Khyber Pakhtunkhwa Prohibition of Employment of Children Act, 2015"]
    assert law_search_candidates({
        "legal_subtype": "road_accident",
        "jurisdiction": "Punjab",
    }) == []
    assert law_search_candidates({
        "legal_subtype": "domestic_violence",
        "jurisdiction": "Pakistan",
    }) == []
    assert law_search_candidates({
        "legal_subtype": "electronic_fraud",
        "jurisdiction": "Khyber Pakhtunkhwa",
    }) == ["Prevention of Electronic Crimes Act, 2016"]
    assert law_search_candidates({
        "legal_subtype": "online_fraud",
        "jurisdiction": "Pakistan",
    }) == ["Prevention of Electronic Crimes Act, 2016"]
    assert law_search_candidates({
        "legal_subtype": "identity_misuse",
        "jurisdiction": "Pakistan",
    }) == []


def test_inactive_sources_are_not_selected(monkeypatch):
    inactive_source = replace(
        next(source for source in source_registry.LEGAL_SOURCES if source.name == "Pakistan Code"),
        active=False,
    )
    monkeypatch.setattr(source_registry, "LEGAL_SOURCES", [inactive_source])

    assert get_relevant_sources("Pakistan", "property") == []


def test_statute_catalog_selection_uses_classified_jurisdiction_not_locality(monkeypatch):
    federal_record = LawRecord(
        "Property Act, 2024",
        "https://pakistancode.gov.pk/english/property-act",
        "Federal",
        "pakistancode.gov.pk",
    )
    kp_record = LawRecord(
        "Property Act, 2024",
        "https://kpcode.kp.gov.pk/homepage/lawDetails/1",
        "Khyber Pakhtunkhwa",
        "kpcode.kp.gov.pk",
    )
    federal_fetch = Mock(return_value=[federal_record])
    kp_fetch = Mock(return_value=[kp_record])
    monkeypatch.setattr("app.legal_sources.statute_retriever._cached_federal_catalog", federal_fetch)
    monkeypatch.setattr("app.legal_sources.statute_retriever._fetch_kp_catalog", kp_fetch)

    assert find_law_records(["Property Act, 2024"], "Federal") == [federal_record]
    federal_fetch.assert_called_once()
    kp_fetch.assert_not_called()

    federal_fetch.reset_mock()
    assert find_law_records(["Property Act, 2024"], "Khyber Pakhtunkhwa") == [kp_record, federal_record]
    federal_fetch.assert_called_once()
    kp_fetch.assert_called_once()

    federal_fetch.reset_mock()
    kp_fetch.reset_mock()
    assert find_law_records(["Property Act, 2024"], "Unknown") == []
    federal_fetch.assert_not_called()
    kp_fetch.assert_not_called()


def test_statute_catalog_does_not_infer_kp_from_chitral():
    with patch(
        "app.legal_sources.statute_retriever._cached_federal_catalog",
        return_value=[],
    ) as federal_catalog, patch(
        "app.legal_sources.statute_retriever._fetch_kp_catalog",
        return_value=[],
    ) as kp_catalog:
        assert find_law_records(["Property Act"], "Unknown") == []
        assert find_law_records(["Property Act"], "Chitral") == []

    federal_catalog.assert_not_called()
    kp_catalog.assert_not_called()


def test_retrieved_evidence_remains_unverified(monkeypatch):
    source = next(source for source in get_relevant_sources("Pakistan", "identity documents"))
    monkeypatch.setattr(evidence_retriever, "find_relevant_links", lambda *_args: ["https://www.nadra.gov.pk/lost-cnic"])
    monkeypatch.setattr(evidence_retriever, "find_best_page", lambda *_args: (
        "https://www.nadra.gov.pk/lost-cnic",
        "CNIC replacement procedure and documents",
    ))
    monkeypatch.setattr(
        evidence_retriever,
        "find_relevant_text",
        lambda *_args: "CNIC replacement procedure and documents",
    )

    evidence = evidence_retriever.collect_evidence(
        [source],
        ["What is the CNIC replacement procedure?"],
    )

    assert len(evidence) == 1
    assert evidence[0].verified is False
    assert evidence[0].retrieval_method == "official_html_page"
    assert evidence[0].retrieved_at


def test_unavailable_registered_source_is_skipped_safely(monkeypatch):
    source = next(source for source in get_relevant_sources("Pakistan", "identity documents"))

    def unavailable(*_args, **_kwargs):
        raise evidence_retriever.requests.ConnectionError("offline")

    monkeypatch.setattr(evidence_retriever, "find_relevant_links", unavailable)

    assert evidence_retriever.collect_evidence([source], ["CNIC replacement procedure"]) == []


def test_off_domain_redirect_is_rejected():
    source = next(
        source
        for source in get_relevant_sources("Pakistan", "identity documents")
        if source.name == "NADRA"
    )
    response = Mock()
    response.url = "https://example.com/redirect"
    response.headers = {"content-type": "text/html"}
    response.raise_for_status = Mock()
    with patch("app.legal_sources.evidence_retriever.requests.get", return_value=response):
        try:
            evidence_retriever.fetch_url_text(source, "https://www.nadra.gov.pk/lost-cnic")
        except ValueError as error:
            assert "redirected outside" in str(error)
        else:
            raise AssertionError("off-domain redirect was accepted")


def test_source_health_checks_redirect_content_and_page_change(monkeypatch):
    source = LegalSource(
        name="KP Police",
        authority="Police Department, Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="police_authority",
        domain="Police reporting",
        official_domain="kppolice.gov.pk",
        search_url="https://kppolice.gov.pk/",
    )
    response = Mock()
    response.url = "https://www.kppolice.gov.pk/"
    response.content = b"<html><body>Police contact information</body></html>"
    response.text = response.content.decode()
    response.headers = {"content-type": "text/html; charset=utf-8"}
    response.raise_for_status = Mock()
    monkeypatch.setattr(source_health.requests, "get", lambda *_args, **_kwargs: response)

    result = source_health.check_source_health(source, previous_content_hash="old-hash")

    assert result["available"] is True
    assert result["redirected"] is True
    assert result["redirect_within_domain"] is True
    assert result["content_accessible"] is True
    assert result["page_changed"] is True
    assert result["freshness_status"] == "changed_since_last_check"
    assert result["status"] == "available"
    assert result["checked_at"]
    assert result["content_hash"]

    unchanged = source_health.check_source_health(
        source,
        previous_content_hash=result["content_hash"],
    )
    assert unchanged["freshness_status"] == "unchanged_since_last_check"


def test_source_health_marks_unextractable_pdf_as_unreadable(monkeypatch):
    source = LegalSource(
        name="Unreadable document",
        authority="Government department",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="legislation",
        domain="Legal information",
        official_domain="example.gov.pk",
        search_url="https://example.gov.pk/law.pdf",
    )
    response = Mock()
    response.url = source.search_url
    response.content = b"not a PDF"
    response.text = ""
    response.headers = {"content-type": "application/pdf"}
    response.raise_for_status = Mock()
    monkeypatch.setattr(source_health.requests, "get", lambda *_args, **_kwargs: response)

    result = source_health.check_source_health(source)

    assert result["status"] == "unreadable"
    assert result["content_accessible"] is False
    assert result["freshness_status"] == "unknown"


def test_source_health_flags_external_redirect_and_outage(monkeypatch):
    source = get_relevant_sources("Pakistan", "identity documents")[0]
    response = Mock()
    response.url = "https://example.com/redirect"
    response.content = b"<html><body>Unexpected redirect</body></html>"
    response.text = response.content.decode()
    response.headers = {"content-type": "text/html"}
    response.raise_for_status = Mock()
    monkeypatch.setattr(source_health.requests, "get", lambda *_args, **_kwargs: response)

    result = source_health.check_source_health(source)

    assert result["redirected"] is True
    assert result["redirect_within_domain"] is False

    def unavailable(*_args, **_kwargs):
        raise source_health.requests.ConnectionError("offline")

    monkeypatch.setattr(source_health.requests, "get", unavailable)
    outage = source_health.check_source_health(source)

    assert outage["available"] is False
    assert outage["content_accessible"] is False
    assert outage["error"] == "ConnectionError"


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
            "relevant_text": "Section 378 defines theft.",
            "official_status": "Under Review",
        }],
        "verification": [{
            "claim": "Which provision addresses theft?",
            "status": "supported",
            "evidence_used": [{
                "source_url": "https://pakistancode.gov.pk/pdffiles/example.pdf",
            }],
        }],
    })

    assert "Your to-do list:" in text
    assert "section 378" in text
    assert "https://pakistancode.gov.pk/pdffiles/example.pdf" in text
    assert "under review" in text.lower()
    assert "Section 378 defines theft." in text
    assert "Which provision addresses theft?" in text


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

    assert "Muamlay ka khulasa:" not in text
    assert "Filhal hum yeh bata sakte hain:" not in text
    assert "Roman Urdu mein jawab." in text
    assert "Aap ke aglay qadam:" in text
    assert "Case summary:" not in text
    assert format_case_response({"status": "needs_description"}, labels) == "Mukhtasaran batayein kya hua."


def test_chat_clarification_response_shows_questions_without_guidance():
    text = format_case_response({
        "status": "needs_clarification",
        "intake": {"problem_summary": "An employment concern."},
        "follow_up": {
            "conversational_message": (
                "I understand that your employer has not paid you. "
                "When were the wages due, and have you raised this with anyone?"
            ),
            "questions": ["When were the wages due?", "Have you raised this with anyone?"],
        },
        "response": {},
    })

    assert text.startswith("I understand")
    assert "When were the wages due" in text
    assert "Case summary:" not in text
    assert "To understand your situation, please clarify" not in text
    assert "1." not in text
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


def test_follow_up_agent_uses_full_context_and_returns_questions_as_a_batch(monkeypatch):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "conversational_message": "I understand. Where is the land, and who owns it?",
            "questions": ["Which district?", "Who owns the land?"],
            "reason": "Need details.",
        }),
        json.dumps({
            "research_ready": False,
            "question_checks": [
                {"question_index": 0, "status": "unanswered", "reason": "No location answer appears in the history."},
                {"question_index": 1, "status": "unanswered", "reason": "No ownership answer appears in the history."},
            ],
            "conversational_message": "I understand the land was left to the heirs. Where is it located, and who owns it?",
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )
    history = [
        {"role": "user", "content": "My brother died in Chitral and left agricultural land. There are three heirs."},
        *[
            {
                "role": "assistant" if index % 2 == 0 else "user",
                "content": f"Earlier message {index} with case context.",
            }
            for index in range(10)
        ],
    ]

    result = followup_agent.generate_follow_up_questions(
        user_message="What documents do we need?",
        intake_data={
            "problem_summary": "The user's brother died in Chitral and left agricultural land for three heirs.",
            "facts": ["brother died", "Chitral", "agricultural land", "three heirs"],
        },
        classification_data={"jurisdiction": "Khyber Pakhtunkhwa", "locality": "Chitral"},
        conversation_history=history,
    )

    assert result.questions == ["Which district?", "Who owns the land?"]
    assert result.conversational_message.startswith("I understand")
    assert result.needs_follow_up is True
    assert "agricultural land. There are three heirs." in prompts[0]
    assert "What documents do we need?" in prompts[0]
    assert "Ask for them together in one concise batch" in prompts[0]
    assert "Do not repeat questions already asked" in prompts[0]
    assert "Research using known information by default" in prompts[0]
    assert "Do not use headings, numbered labels, form language" in prompts[0]
    assert "If the user says they do not know, are unsure, or do not have something, accept that as an answer." in prompts[0]
    assert "COMPLETE PRIOR CONVERSATION:" in prompts[1]
    assert "Which district?" in prompts[1]


def test_follow_up_agent_generates_natural_batch_without_scripted_template(monkeypatch):
    prompts = []
    message = (
        "I understand you are still working in Peshawar and have three months "
        "of unpaid salary. Roughly how much is owed, and have you complained "
        "to an authority yet? If you are unsure, just tell me what you know."
    )
    def generate_response(prompt):
        prompts.append(prompt)
        if "CANDIDATE QUESTIONS:" in prompt:
            return json.dumps({
                "research_ready": False,
                "question_checks": [
                    {"question_index": index, "status": "unanswered", "reason": "This detail may materially change the next step."}
                    for index in range(2)
                ],
                "conversational_message": message,
            })
        return json.dumps({
            "needs_follow_up": True,
            "conversational_message": message,
            "questions": ["Roughly how much is owed?", "Have you complained to an authority yet?"],
            "reason": "These details may affect the appropriate process.",
        })
    monkeypatch.setattr(followup_agent, "generate_response", generate_response)

    result = followup_agent.generate_follow_up_questions(
        user_message="My employer in Peshawar has not paid me for three months.",
        intake_data={
            "problem_summary": "Employer has not paid salary for three months.",
            "facts": ["Peshawar", "three months unpaid salary", "still employed"],
        },
        classification_data={
            "legal_domain": "employment",
            "jurisdiction": "Khyber Pakhtunkhwa",
            "locality": "Peshawar",
        },
    )
    rendered = format_case_response({
        "status": "needs_clarification",
        "intake": {"problem_summary": "Employer has not paid salary for three months."},
        "follow_up": result.model_dump(),
    })

    assert rendered == message
    assert len(result.questions) == 2
    assert "To understand your situation, please clarify" not in rendered
    assert "Please answer the following questions" not in rendered
    assert "Question 1" not in rendered
    assert "Case summary:" not in rendered
    assert "conversational_message as the complete" in prompts[0]
    assert "Include every question from questions exactly once" in prompts[0]


def test_follow_up_agent_drops_a_question_already_asked(monkeypatch):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "questions": ["Which district?"],
            "reason": "Need jurisdiction.",
        }),
        json.dumps({
            "research_ready": True,
            "question_checks": [
                {"question_index": 0, "status": "answered", "reason": "The user identified Chitral."},
            ],
            "conversational_message": "",
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )

    result = followup_agent.generate_follow_up_questions(
        user_message="What documents are needed?",
        intake_data={"facts": ["The property is in Chitral."]},
        classification_data={"locality": "Chitral"},
        conversation_history=[
            {"role": "assistant", "content": "Which district is the land in?"},
            {"role": "user", "content": "The property is in Chitral."},
        ],
    )

    assert result.needs_follow_up is False
    assert result.questions == []
    assert "The property is in Chitral." in prompts[1]
    assert "Which district?" in prompts[1]


@pytest.mark.parametrize(
    ("user_message", "facts", "classification", "history", "model_questions", "expected_count"),
    [
        (
            "My employer in Peshawar has not paid my salary for three months.",
            ["Peshawar", "salary unpaid for three months"],
            {"jurisdiction": "Khyber Pakhtunkhwa", "locality": "Peshawar", "legal_domain": "employment"},
            [],
            ["What type of employer is this?", "Have you already complained to an authority?", "About how much salary is unpaid?"],
            3,
        ),
        (
            "My landlord changed the locks after I missed rent.",
            ["Rented house", "landlord changed the locks", "rent unpaid"],
            {"jurisdiction": "Unknown", "locality": "unknown", "legal_domain": "housing"},
            [],
            ["In which city or district is the rented home?", "Did the landlord give written notice?", "Are your belongings still inside?"],
            3,
        ),
        (
            "My siblings dispute our inherited agricultural land.",
            ["Inherited agricultural land", "siblings dispute ownership"],
            {"jurisdiction": "Unknown", "locality": "unknown", "legal_domain": "property"},
            [],
            ["Where is the land located?", "Has any inheritance or mutation record been started?"],
            2,
        ),
        (
            "Someone is threatening to publish private images online.",
            ["Online threats to publish private images"],
            {"jurisdiction": "Unknown", "locality": "unknown", "legal_domain": "harassment"},
            [],
            ["Which country are you currently in?", "Have you saved the messages or account details?", "Is anyone in immediate danger?"],
            3,
        ),
        (
            "My employer withheld my wages. Where can I complain?",
            ["Wages withheld"],
            {"jurisdiction": "Unknown", "locality": "unknown", "legal_domain": "employment"},
            [],
            ["Which city or district did this happen in?", "What type of workplace is it?"],
            2,
        ),
        (
            "My employer in Lahore withheld two months' salary; I have my contract and bank records.",
            ["Lahore", "two months' salary withheld", "contract", "bank records"],
            {"jurisdiction": "Punjab", "locality": "Lahore", "legal_domain": "employment"},
            [],
            [],
            0,
        ),
        (
            "I need help with unpaid salary.",
            ["Unpaid salary"],
            {"jurisdiction": "Unknown", "locality": "unknown", "legal_domain": "employment"},
            [
                {"role": "assistant", "content": "Which city did this happen in?"},
                {"role": "user", "content": "It is in Lahore at a private shop."},
            ],
            ["Which city did this happen in?", "How much salary is unpaid?"],
            1,
        ),
    ],
)
def test_follow_up_questions_are_case_specific_batches_and_skip_known_or_answered_facts(
    monkeypatch,
    user_message,
    facts,
    classification,
    history,
    model_questions,
    expected_count,
):
    prompts = []
    def generate_follow_up_response(prompt):
        prompts.append(prompt)
        if "CANDIDATE QUESTIONS:" in prompt:
            return json.dumps({
                "research_ready": False,
                "question_checks": [
                    {
                        "question_index": index,
                        "status": "answered" if history and index == 0 else "unanswered",
                        "reason": (
                            "The conversation contains the answer."
                            if history and index == 0
                            else "This detail remains relevant to this case."
                        ),
                    }
                    for index in range(len(model_questions))
                ],
                "conversational_message": "What amount remains unpaid?",
            })
        return json.dumps({
            "needs_follow_up": bool(model_questions),
            "questions": model_questions,
            "reason": "Only the remaining material facts are requested.",
        })

    monkeypatch.setattr(followup_agent, "generate_response", generate_follow_up_response)

    result = followup_agent.generate_follow_up_questions(
        user_message=user_message,
        intake_data={"problem_summary": user_message, "facts": facts},
        classification_data=classification,
        conversation_history=history,
    )

    assert len(result.questions) == expected_count
    assert result.needs_follow_up is bool(expected_count)
    assert user_message in prompts[0]
    if history:
        assert len(prompts) == 2
        assert "It is in Lahore at a private shop." in prompts[1]
    for fact in facts:
        assert fact in prompts[0]
    for message in history:
        assert message["content"] in prompts[0]
    assert "Ask for them together in one concise batch" in prompts[0]
    assert "After the user answers a batch, perform a final sufficiency check" in prompts[0]


def test_follow_up_question_batch_is_bounded_and_deduplicated(monkeypatch):
    questions = [f"Question {index}?" for index in range(10)]
    questions.extend(["Question 1?", ""])

    def generate_response(prompt):
        if "CANDIDATE QUESTIONS:" in prompt:
            return json.dumps({
                "research_ready": False,
                "question_checks": [
                    {"question_index": index, "status": "unanswered", "reason": "Candidate retained for this bounded-batch test."}
                    for index in range(8)
                ],
                "conversational_message": "I have a few questions that will help determine the next step.",
            })
        return json.dumps({"questions": questions})

    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        generate_response,
    )

    result = followup_agent.generate_follow_up_questions(
        user_message="I need help.",
        intake_data={},
        classification_data={},
    )

    assert result.questions == questions[:8]
    assert result.needs_follow_up is True


def test_conversation_response_formats_entire_clarification_batch():
    response = format_case_response({
        "status": "needs_clarification",
        "intake": {"problem_summary": "A wage dispute."},
        "follow_up": {
            "conversational_message": (
                "I understand there is a wage dispute. Which city did this happen in, "
                "what type of workplace is it, and have you already complained?"
            ),
            "questions": [
                "Which city did this happen in?",
                "What type of workplace is it?",
                "Have you already complained?",
            ],
        },
    })

    assert response.startswith("I understand there is a wage dispute.")
    assert "1." not in response
    assert "2." not in response
    assert "3." not in response
    assert "To understand your situation, please clarify" not in response


def test_user_unknown_answer_is_valid_and_not_reasked(monkeypatch):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "conversational_message": "Do you know when the notice was sent?",
            "questions": ["Do you know when the notice was sent?"],
            "reason": "Notice timing may matter.",
        }),
        json.dumps({
            "research_ready": True,
            "question_checks": [
                {"question_index": 0, "status": "unknown", "reason": "The user said they do not know and received nothing in writing."},
            ],
            "conversational_message": "",
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )
    history = [
        {"role": "assistant", "content": "Did your landlord give you written notice?"},
        {"role": "user", "content": "I don't know; I did not receive anything in writing."},
    ]

    result = followup_agent.generate_follow_up_questions(
        user_message="I still cannot find a notice.",
        intake_data={
            "problem_summary": "The landlord changed the locks.",
            "facts": ["The user does not know whether written notice was given."],
        },
        classification_data={"legal_domain": "housing", "jurisdiction": "Punjab"},
        conversation_history=history,
    )

    assert "Did your landlord give you written notice?" not in result.questions
    assert "I don't know; I did not receive anything in writing." in prompts[0]
    assert "I don't know; I did not receive anything in writing." in prompts[1]
    assert result.questions == []
    assert result.conversational_message == ""


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ("I don't know.", "unknown"),
        ("I don't remember.", "unknown"),
        ("There was no specific date.", "unknown"),
        ("Yes, I have WhatsApp messages about the deposit.", "answered"),
        ("I moved out about two months ago.", "approximate_sufficient"),
    ],
)
def test_semantic_review_accepts_unknown_negative_and_approximate_answers(
    monkeypatch,
    answer,
    status,
):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "conversational_message": "Could you clarify the date?",
            "questions": ["What exact date was that?"],
            "reason": "Check timeline.",
        }),
        json.dumps({
            "research_ready": True,
            "question_checks": [
                {"question_index": 0, "status": status, "reason": f"The user said: {answer}"},
            ],
            "conversational_message": "",
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )

    result = followup_agent.generate_follow_up_questions(
        user_message="I have already shared what I know.",
        intake_data={"facts": [answer]},
        classification_data={"jurisdiction": "Punjab", "locality": "Lahore"},
        conversation_history=[
            {"role": "assistant", "content": "When was this?"},
            {"role": "user", "content": answer},
        ],
    )

    assert result.questions == []
    assert result.needs_follow_up is False
    assert result.conversational_message == ""
    assert answer in prompts[1]


def test_semantic_review_allows_material_exact_date_with_reason_and_optional_wording(monkeypatch):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "conversational_message": "What exact date did you move out?",
            "questions": ["What exact date did you move out?"],
            "reason": "The move-out date may affect the timeline.",
        }),
        json.dumps({
            "research_ready": False,
            "question_checks": [
                {
                    "question_index": 0,
                    "status": "precision_material",
                    "reason": "The exact date is needed to calculate a legally relevant filing period.",
                },
            ],
            "conversational_message": (
                "I have the approximate timing. If you remember the exact move-out date, "
                "it would help me check the timeline; if not, that is okay and I can proceed."
            ),
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )

    result = followup_agent.generate_follow_up_questions(
        user_message="I moved out about two months ago.",
        intake_data={"facts": ["Moved out about two months ago."]},
        classification_data={"jurisdiction": "Punjab"},
        conversation_history=[{"role": "assistant", "content": "When did you move out?"}],
    )

    assert result.questions == ["What exact date did you move out?"]
    assert "if not, that is okay" in result.conversational_message
    assert "genuinely necessary" in prompts[1]


def test_security_deposit_answers_across_turns_are_not_asked_again_and_pipeline_researches(monkeypatch):
    prompts = []
    responses = iter([
        json.dumps({
            "needs_follow_up": True,
            "conversational_message": "Could you clarify the dates, evidence, and complaint status?",
            "questions": [
                "What exact date did you move out?",
                "What specific return date did the landlord promise?",
                "Do you have evidence of the property's condition?",
                "Have you made a formal complaint?",
                "What is your landlord's full name, phone number, and address?",
            ],
            "reason": "Potential timeline, evidence, and process details.",
        }),
        json.dumps({
            "research_ready": True,
            "question_checks": [
                {"question_index": 0, "status": "approximate_sufficient", "reason": "The user said about two months ago; exact day is not necessary to begin research."},
                {"question_index": 1, "status": "unknown", "reason": "The user said the landlord gave no specific return date."},
                {"question_index": 2, "status": "answered", "reason": "The user already has photos showing the property's condition."},
                {"question_index": 3, "status": "answered", "reason": "The user has not made a formal complaint."},
                {"question_index": 4, "status": "unanswered", "reason": "Personal identifiers are unnecessary for general legal analysis."},
            ],
            "conversational_message": "",
        }),
    ])
    monkeypatch.setattr(
        followup_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or next(responses),
    )

    intake = Model({
        "problem_summary": "A tenant moved out and seeks return of a security deposit.",
        "facts": [
            "The rental property is in Peshawar, Khyber Pakhtunkhwa.",
            "Moved out about two months ago",
            "The user does not know the exact move-out date.",
            "Landlord gave no specific return date and said he would pay later",
            "WhatsApp messages about the deposit exist",
            "Security deposit is Rs. 80,000",
            "The rental agreement and payment receipts are available.",
            "Photos showing the property's condition are available.",
            "The user has not made a formal complaint.",
            "The user says this is all the information they have.",
        ],
        "missing_information": [],
    })
    classification = Model({
        "legal_domain": "tenancy",
        "matter_type": "security deposit",
        "jurisdiction": "Khyber Pakhtunkhwa",
        "locality": "Peshawar",
    })
    for name, value in classification.data.items():
        setattr(classification, name, value)
    research = research_agent.ResearchResult(
        research_questions=["Which authority handles a security deposit dispute?"],
    )
    research_call = Mock(return_value=research)
    source = EvidenceItem(
        source_name="KP Labour Department",
        source_url="https://labour.kp.gov.pk/tenancy",
        source_title="Tenant dispute guidance",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="government",
        relevant_text="Official information about the relevant complaint route.",
        citation="Tenant dispute guidance",
    )
    final_response = Model({
        "answer": "The available official material identifies a route to raise the dispute.",
        "next_steps": ["Contact the relevant authority using its published complaint process."],
        "documents_needed": ["Keep the rental agreement, receipts, messages, and condition photos."],
        "authorities": ["KP Labour Department"],
        "sources": [],
        "uncertainty": [],
        "disclaimer": "This is legal information, not legal advice.",
    })

    def supported_verification(_claim, evidence, **_kwargs):
        return Model({
            "status": "supported",
            "supported": True,
            "confidence": "high",
            "reasoning": "The official source supports the claim.",
            "evidence_used": [item.model_dump() for item in evidence],
            "uncertainty": [],
        })

    monkeypatch.setattr(orchestrator, "intake_case", lambda *_args, **_kwargs: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "create_research_plan", research_call)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: EvidenceGapPlan())
    monkeypatch.setattr(orchestrator, "get_relevant_sources", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "collect_evidence", lambda *_args: [source])
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", lambda *_args: [])
    monkeypatch.setattr(orchestrator, "verify_claim", supported_verification)
    final_response_call = Mock(return_value=final_response)
    monkeypatch.setattr(orchestrator, "generate_final_response", final_response_call)

    history = [
        {"role": "user", "content": "My landlord in Peshawar, KP has not returned my Rs. 80,000 security deposit after I moved out. I have a rental agreement and payment receipts."},
        {"role": "assistant", "content": "When did you move out, what return date did the landlord give, and what evidence do you have? Have you complained, and what is the landlord's contact information?"},
        {"role": "user", "content": "I moved out about two months ago, but I don't know the exact date. The landlord never gave a specific return date; he only said he'd pay later."},
        {"role": "user", "content": "I have WhatsApp messages about the deposit and photos showing the property's condition."},
        {"role": "user", "content": "I haven't made a formal complaint. That's all the information I have."},
    ]
    result = process_case(
        "I don't remember the exact move-out date.",
        conversation_history=history,
    )

    assert result["status"] == "completed"
    assert result["follow_up"]["questions"] == []
    research_call.assert_called_once()
    final_response_call.assert_called_once()
    assert result["response"]["answer"] == final_response.data["answer"]
    assert result["response"]["documents_needed"] == final_response.data["documents_needed"]
    assert result["evidence"][0]["source_url"] == source.source_url
    assert result["verification"][0]["status"] == "supported"
    assert "Peshawar" in prompts[1]
    assert "about two months ago" in prompts[1]
    assert "never gave a specific return date" in prompts[1]
    assert "WhatsApp messages" in prompts[1]
    assert "photos" in prompts[1]
    assert "Rs. 80,000" in prompts[1]
    assert "That's all the information I have." in prompts[1]


def test_final_response_prompt_acknowledges_answered_details_naturally(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        response_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or json.dumps({"answer": "A supported answer."}),
    )

    response_agent.generate_final_response(
        user_message="I have not complained yet.",
        intake_data={
            "problem_summary": "Salary was unpaid in Peshawar.",
            "facts": ["The user has not complained", "Rs. 100,000 is unpaid"],
        },
        classification_data={"jurisdiction": "Khyber Pakhtunkhwa", "locality": "Peshawar"},
        evidence=[],
        verification_results=[],
    )

    assert "acknowledge the new details" in prompts[0]
    assert "move into the findings" in prompts[0]
    assert "repeat a full" in prompts[0]
    assert "case summary" in prompts[0]
    assert "use a heading as the opening" in prompts[0]


def test_research_plan_decomposes_material_legal_questions(monkeypatch):
    prompts = []
    questions = [
        "Which inheritance rules apply?",
        "Which authority records the inheritance?",
        "What procedure must the heirs follow?",
        "Which documents are established as required?",
        "Are deadlines or conditions established?",
        "Which jurisdiction applies?",
    ]
    monkeypatch.setattr(
        research_agent,
        "generate_response",
        lambda prompt: prompts.append(prompt) or json.dumps({
            "research_questions": questions,
            "source_types": ["revenue department"],
            "priority_jurisdictions": ["Federal", "Punjab"],
        }),
    )

    plan = research_agent.create_research_plan(
        {"facts": ["deceased brother", "Chitral", "agricultural land", "three heirs"]},
        {"jurisdiction": "Khyber Pakhtunkhwa", "locality": "Chitral"},
    )

    assert plan.research_questions == questions
    assert plan.source_types == ["revenue department"]
    assert plan.priority_jurisdictions == ["Khyber Pakhtunkhwa", "Federal"]
    assert "do not collapse these into one generic search" in prompts[0]
    assert "Chitral" in prompts[0]


def test_research_plan_does_not_infer_unknown_jurisdiction_from_locality(monkeypatch):
    monkeypatch.setattr(
        research_agent,
        "generate_response",
        lambda _prompt: json.dumps({
            "research_questions": ["Which law applies?"],
            "priority_jurisdictions": ["Khyber Pakhtunkhwa"],
        }),
    )

    plan = research_agent.create_research_plan(
        {"facts": ["The issue happened in Chitral."]},
        {"jurisdiction": "Unknown", "locality": "Chitral"},
    )

    assert plan.priority_jurisdictions == []


def test_verifier_marks_silence_unresolved_without_calling_model(monkeypatch):
    generate = Mock(side_effect=AssertionError("no relevant evidence should not be model-verified"))
    monkeypatch.setattr(verification_agent, "generate_response", generate)

    result = verify_claim("Which documents are required for inheritance mutation?", [])

    assert result.status == "unresolved"
    assert result.supported is False
    assert result.evidence_used == []
    generate.assert_not_called()


def test_verifier_unresolved_fallback_uses_requested_language():
    urdu = verify_claim("Which authority?", [], language="ur")
    roman_urdu = verify_claim("Which authority?", [], language="roman_urdu")

    assert "حاصل شدہ شواہد" in urdu.reasoning
    assert "Hasil shuda" in roman_urdu.reasoning


def test_verifier_accepts_supported_or_contradicted_only_with_matched_evidence(monkeypatch):
    source = EvidenceItem(
        source_name="KP Revenue Department",
        source_url="https://revenue.kp.gov.pk/service",
        source_title="Inheritance mutation",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="government",
        relevant_text="The revenue authority records inherited agricultural land.",
    )
    for status, supported in (("supported", True), ("contradicted", False)):
        monkeypatch.setattr(
            verification_agent,
            "generate_response",
            lambda _prompt, status=status, supported=supported: json.dumps({
                "claim": "Which authority records inherited agricultural land?",
                "status": status,
                "supported": supported,
                "confidence": "high",
                "reasoning": "The supplied source addresses the authority.",
                "evidence_used": [source.source_url],
                "uncertainty": [],
            }),
        )

        result = verify_claim("Which authority records inherited agricultural land?", [source])

        assert result.status == status
        assert result.supported is supported
        assert result.evidence_used == [source]


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

    assert "Begin by briefly acknowledging relevant facts the user actually shared" in prompts[0]
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
        "questions": [
            "Which outcome are you seeking?",
            "Has the other party responded to your request?",
        ],
        "reason": "These facts may materially affect the relevant process.",
    })
    research = Mock(side_effect=AssertionError("research should wait for clarification"))
    evidence = Mock(side_effect=AssertionError("evidence retrieval should wait for clarification"))
    prompts = []
    follow_up_calls = []

    monkeypatch.setattr(orchestrator, "intake_case", lambda message, **_kwargs: prompts.append(message) or intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda *_args: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **kwargs: follow_up_calls.append(kwargs) or follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", research)
    monkeypatch.setattr(orchestrator, "collect_evidence", evidence)

    history = [
        {"role": "user", "content": "My brother died in Chitral and left agricultural land. There are three heirs."},
        {"role": "assistant", "content": "What documents do you need?"},
    ]
    result = process_case("What documents do we need?", conversation_history=history)

    assert result["status"] == "needs_clarification"
    assert result["follow_up"]["questions"] == [
        "Which outcome are you seeking?",
        "Has the other party responded to your request?",
    ]
    assert "My brother died in Chitral" in prompts[0]
    assert "What documents do we need?" in prompts[0]
    assert follow_up_calls[0]["conversation_history"] == history
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
        "source_types": ["labour department"],
        "priority_jurisdictions": ["Punjab"],
        "evidence_needed": [],
        "laws_to_check": ["Punjab Payment of Wages Act"],
    })
    research.research_questions = research.data["research_questions"]
    research.evidence_needed = research.data["evidence_needed"]
    research.laws_to_check = research.data["laws_to_check"]
    final = Model({"answer": "Sourced answer."})
    statute_lookup = Mock(return_value=[])
    evidence_lookup = Mock(return_value=[])
    source_lookup = Mock(return_value=[])

    monkeypatch.setattr(orchestrator, "intake_case", lambda _, **__: intake)
    monkeypatch.setattr(orchestrator, "classify_case", lambda _: classification)
    monkeypatch.setattr(orchestrator, "generate_follow_up_questions", lambda **_: follow_up)
    monkeypatch.setattr(orchestrator, "create_research_plan", lambda *_: research)
    monkeypatch.setattr(orchestrator, "identify_evidence_gaps", lambda *_args, **_kwargs: EvidenceGapPlan())
    monkeypatch.setattr(orchestrator, "get_relevant_sources", source_lookup)
    monkeypatch.setattr(orchestrator, "collect_evidence", evidence_lookup)
    monkeypatch.setattr(orchestrator, "collect_statute_evidence", statute_lookup)
    monkeypatch.setattr(orchestrator, "verify_claim", lambda claim, _: Model({"claim": claim}))
    monkeypatch.setattr(orchestrator, "generate_final_response", lambda **_: final)

    result = process_case("My employer withheld wages.")

    assert result["status"] == "evidence_unavailable"
    assert statute_lookup.call_args.args[0] == ["Punjab Payment of Wages Act"]
    assert statute_lookup.call_args.args[1] == ["Minimum wage and wage recovery procedure"]
    assert statute_lookup.call_args.args[2] == "Punjab"
    assert source_lookup.call_args.args[3:5] == (["Punjab"], ["labour department"])
    assert "My employer withheld wages." in source_lookup.call_args.args[5]
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
        lambda claim, available, **_kwargs: Model({
            "claim": claim,
            "status": "supported",
            "supported": True,
            "evidence_used": [item.model_dump() for item in available],
        }),
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
    def verify(claim, _evidence, **_kwargs):
        supported = claim != "The retrieved source addresses notice requirements."
        return Model({
            "claim": claim,
            "status": "supported" if supported else "unresolved",
            "supported": supported,
            "evidence_used": [evidence_item.model_dump()] if supported else [],
        })

    monkeypatch.setattr(orchestrator, "verify_claim", verify)
    monkeypatch.setattr(orchestrator, "generate_final_response", lambda **_kwargs: final)

    result = process_case("A tenant received a written notice.")

    assert result["status"] == "completed"
    assert result["response"]["answer"] == "The available official evidence does not establish a verified answer to this request."
    assert result["response"]["next_steps"] == []
    assert result["response"]["documents_needed"] == []
    assert result["evidence"][0]["citation"] == "Tenancy law"