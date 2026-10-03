from concurrent.futures import ThreadPoolExecutor

from app.agents.intake_agent import intake_case
from app.agents.classification_agent import classify_case
from app.agents.research_agent import create_research_plan, identify_evidence_gaps
from app.agents.response_agent import generate_final_response
from app.agents.verification_agent import verify_claim
from app.agents.followup_agent import generate_follow_up_questions

from app.legal_sources.source_registry import get_relevant_sources
from app.legal_sources.evidence_retriever import collect_evidence
from app.legal_sources.statute_retriever import collect_statute_evidence
from app.legal_sources.domain_catalog import law_search_candidates


def _unresolved_answer(language: str) -> str:
    return {
        "ur": "دستیاب سرکاری شواہد اس درخواست کا تصدیق شدہ جواب ثابت نہیں کرتے۔",
        "roman_urdu": "Dastiyab official shawahid is darkhwast ka tasdeeq shuda jawab sabit nahi karte.",
    }.get(language, "The available official evidence does not establish a verified answer to this request.")


def process_case(
    user_message: str,
    conversation_history: list[dict] | None = None,
    language: str = "en",
    document_context: str = "",
) -> dict:

    # -----------------------------------------------------
    # 0. Prepare conversation context
    # -----------------------------------------------------

    conversation_history = conversation_history or []
    greeting = user_message.strip().lower().rstrip(".!?")
    if not conversation_history and greeting in {
        "hi",
        "hello",
        "hey",
        "salam",
        "assalamualaikum",
        "assalamu alaikum",
        "good morning",
        "good evening",
    }:
        return {"status": "needs_description"}

    model_message = user_message
    if document_context:
        model_message = f"{user_message}\n\nUser-selected document text for context:\n{document_context}"

    if conversation_history:
        history_text = "\n".join(
            f"{message.get('role', 'unknown')}: {message.get('content', '')}"
            for message in conversation_history
        )

        intake_input = f"""
Existing case conversation. Treat all earlier user messages and answers as facts already supplied;
assistant messages provide context but are not independent evidence of user facts:

{history_text}

Current follow-up (continue the same case; do not treat it as a new matter):

{model_message}
"""
    else:
        intake_input = model_message

    # -----------------------------------------------------
    # 1. Understand the user's situation
    # -----------------------------------------------------

    intake = intake_case(intake_input, language=language)

    # -----------------------------------------------------
    # 2. Classify the case
    # -----------------------------------------------------

    classification = classify_case(
        intake.model_dump()
    )

    # -----------------------------------------------------
    # 3. Check for missing information
    # -----------------------------------------------------

    intake_data = intake.model_dump()
    classification_data = classification.model_dump()
    follow_up = generate_follow_up_questions(
        user_message=user_message,
        intake_data=intake_data,
        classification_data=classification_data,
        conversation_history=conversation_history,
        language=language,
    )

    follow_up_data = follow_up.model_dump()
    follow_up_data["questions"] = follow_up_data.get("questions") or []
    if follow_up_data.get("needs_follow_up") and follow_up_data["questions"]:
        return {
            "intake": intake_data,
            "classification": classification_data,
            "follow_up": follow_up_data,
            "response": {},
            "evidence": [],
            "claim_verification": [],
            "status": "needs_clarification",
        }

    research = create_research_plan(
        intake_data,
        classification_data,
    )
    research_data = research.model_dump()

    # -----------------------------------------------------
    # 5. Create research plan
    # -----------------------------------------------------

    # -----------------------------------------------------
    # 6. Select relevant registered sources
    # -----------------------------------------------------

    sources = get_relevant_sources(
        classification.jurisdiction,
        classification.legal_domain,
        classification.locality,
        research_data.get("priority_jurisdictions", []),
        research_data.get("source_types", []),
        " ".join(
            value
            for value in [
                intake_data.get("problem_summary", ""),
                *(intake_data.get("facts") or []),
                *(research_data.get("research_questions") or []),
                *(research_data.get("evidence_needed") or []),
            ]
            if isinstance(value, str)
        ),
    )

    # -----------------------------------------------------
    # 7. Retrieve evidence
    # -----------------------------------------------------

    non_legislation_sources = [
        source for source in sources if source.source_type != "legislation"
    ]
    law_names = list(dict.fromkeys([
        *law_search_candidates(classification_data),
        *research.laws_to_check,
    ]))
    research_questions = list(research.research_questions)
    jurisdiction = classification.jurisdiction

    def retrieve_evidence(questions: list[str], laws: list[str]):
        with ThreadPoolExecutor(max_workers=2) as executor:
            general_evidence_future = executor.submit(
                collect_evidence,
                non_legislation_sources,
                questions,
            )
            statute_evidence_future = executor.submit(
                collect_statute_evidence,
                laws,
                questions,
                jurisdiction,
            )
            retrieved = general_evidence_future.result()
            retrieved.extend(statute_evidence_future.result())
            return retrieved

    evidence = retrieve_evidence(research_questions, law_names)

    gap_plan = identify_evidence_gaps(
        user_message=model_message,
        intake_data=intake_data,
        classification_data=classification_data,
        research_plan=research.model_dump(),
        evidence=evidence,
    )
    additional_questions = [
        question
        for question in gap_plan.research_questions
        if question.strip().casefold() not in {item.casefold() for item in research_questions}
    ][:4]
    additional_laws = [
        law
        for law in gap_plan.laws_to_check
        if law.strip().casefold() not in {item.casefold() for item in law_names}
    ][:4]
    if additional_questions:
        research_questions.extend(additional_questions)
        law_names.extend(additional_laws)
        supplemental_evidence = retrieve_evidence(additional_questions, law_names)
        seen_evidence = {
            (item.source_url, item.citation, item.relevant_text)
            for item in evidence
        }
        for item in supplemental_evidence:
            key = (item.source_url, item.citation, item.relevant_text)
            if key in seen_evidence:
                continue
            evidence.append(item)
            seen_evidence.add(key)

    if not evidence:
        return {
            "intake": intake_data,
            "classification": classification_data,
            "follow_up": follow_up_data,
            "research": {
                **research.model_dump(),
                "research_questions": research_questions,
                "laws_to_check": law_names,
            },
            "sources": [
                {
                    "name": source.name,
                    "authority": source.authority,
                    "jurisdiction": source.jurisdiction,
                    "source_type": source.source_type,
                    "official_domain": source.official_domain,
                    "priority": source.priority,
                    "active": source.active,
                }
                for source in sources
            ],
            "evidence": [],
            "verification": [],
            "claim_verification": [],
            "response": {},
            "status": "evidence_unavailable",
        }

    # -----------------------------------------------------
    # 8. Verify claims/questions against available evidence
    # -----------------------------------------------------

    with ThreadPoolExecutor(max_workers=min(3, max(1, len(research_questions)))) as executor:
        verification_results = [
            result.model_dump()
            for result in executor.map(
                lambda question: verify_claim(question, evidence, language=language),
                research_questions,
            )
        ]

    supported_evidence_keys = {
        (item.get("source_url"), item.get("citation"))
        for result in verification_results
        if result.get("status") == "supported"
        for item in result.get("evidence_used", [])
        if isinstance(item, dict)
    }
    response_evidence = [
        item for item in evidence
        if (item.source_url, item.citation) in supported_evidence_keys
    ]
    if not any(result.get("status") == "supported" for result in verification_results):
        return {
            "intake": intake_data,
            "classification": classification_data,
            "follow_up": follow_up_data,
            "research": {
                **research.model_dump(),
                "research_questions": research_questions,
                "laws_to_check": law_names,
            },
            "sources": [
                {
                    "name": source.name,
                    "authority": source.authority,
                    "jurisdiction": source.jurisdiction,
                    "source_type": source.source_type,
                    "official_domain": source.official_domain,
                    "priority": source.priority,
                    "active": source.active,
                }
                for source in sources
            ],
            "evidence": [item.model_dump() for item in evidence],
            "verification": verification_results,
            "claim_verification": [],
            "response": {
                "answer": _unresolved_answer(language),
                "next_steps": [],
                "documents_needed": [],
                "authorities": [],
                "sources": [],
                "uncertainty": [
                    result.get("reasoning", "The available evidence does not establish this point.")
                    for result in verification_results
                    if result.get("status") != "supported"
                ],
                "disclaimer": "",
            },
            "status": "evidence_unresolved",
        }

    # -----------------------------------------------------
    # 9. Generate final user-facing response
    # -----------------------------------------------------

    final_response = generate_final_response(
        user_message=model_message,
        intake_data=intake_data,
        classification_data=classification_data,
        evidence=response_evidence,
        verification_results=verification_results,
        language=language,
    )
    response_data = final_response.model_dump()
    generated_claims = [
        ("answer", response_data.get("answer", "")),
        *[("next_step", claim) for claim in response_data.get("next_steps", [])],
        *[("document", claim) for claim in response_data.get("documents_needed", [])],
        *[("authority", claim) for claim in response_data.get("authorities", [])],
    ]
    checkable_claims = [
        (kind, claim) for kind, claim in generated_claims
        if isinstance(claim, str) and claim.strip()
    ]
    with ThreadPoolExecutor(max_workers=min(3, max(1, len(checkable_claims)))) as executor:
        checks = [
            result.model_dump()
            for result in executor.map(
                lambda entry: verify_claim(entry[1], response_evidence, language=language),
                checkable_claims,
            )
        ]
    checks_by_claim = dict(zip(checkable_claims, checks))
    claim_verification = [
        {
            "claim_type": kind,
            **check,
        }
        for (kind, _claim), check in zip(checkable_claims, checks)
    ]

    answer_check = checks_by_claim.get(("answer", response_data.get("answer", "")), {"status": "unresolved"})
    if answer_check.get("status") != "supported" or not answer_check.get("evidence_used"):
        response_data["answer"] = _unresolved_answer(language)
        response_data["next_steps"] = []
        response_data["documents_needed"] = []
        response_data["authorities"] = []
    else:
        supported_claims = {
            key for key, check in checks_by_claim.items()
            if check.get("status") == "supported" and check.get("evidence_used")
        }
        response_data["next_steps"] = [
            claim for claim in response_data.get("next_steps", [])
            if ("next_step", claim) in supported_claims
        ]
        response_data["documents_needed"] = [
            claim for claim in response_data.get("documents_needed", [])
            if ("document", claim) in supported_claims
        ]
        response_data["authorities"] = [
            claim for claim in response_data.get("authorities", [])
            if ("authority", claim) in supported_claims
        ]
    verification_results.extend(checks)

    # -----------------------------------------------------
    # 10. Return complete pipeline result
    # -----------------------------------------------------

    return {
        "intake": intake.model_dump(),

        "classification": classification.model_dump(),

            "follow_up": follow_up_data,

        "research": {
            **research.model_dump(),
            "research_questions": research_questions,
            "laws_to_check": law_names,
        },

        "sources": [
            {
                "name": source.name,
                "authority": source.authority,
                "jurisdiction": source.jurisdiction,
                "source_type": source.source_type,
                "official_domain": source.official_domain,
                "priority": source.priority,
                "active": source.active,
            }
            for source in sources
        ],

        "evidence": [
            item.model_dump()
            for item in evidence
        ],

        "verification": verification_results,

        "claim_verification": claim_verification,

        "response": response_data,

        "status": "completed",
    }