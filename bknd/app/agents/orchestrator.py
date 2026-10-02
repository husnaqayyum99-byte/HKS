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
            f"{message['role']}: {message['content']}"
            for message in conversation_history
        )

        intake_input = f"""
Previous conversation:

{history_text}

Current user message:

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
    follow_up_data["questions"] = (follow_up_data.get("questions") or [])[:3]
    if follow_up_data.get("needs_follow_up") and follow_up_data["questions"]:
        return {
            "intake": intake_data,
            "classification": classification_data,
            "follow_up": follow_up_data,
            "response": {},
            "evidence": [],
            "status": "needs_clarification",
        }

    research = create_research_plan(
        intake_data,
        classification_data,
    )

    # -----------------------------------------------------
    # 5. Create research plan
    # -----------------------------------------------------

    # -----------------------------------------------------
    # 6. Select relevant registered sources
    # -----------------------------------------------------

    sources = get_relevant_sources(
        classification.jurisdiction,
        classification.legal_domain,
    )

    # -----------------------------------------------------
    # 7. Retrieve evidence
    # -----------------------------------------------------

    non_legislation_sources = [
        source for source in sources if source.source_type != "legislation"
    ]
    law_names = list(research.laws_to_check)
    research_questions = list(research.research_questions)
    jurisdiction = f"{classification.jurisdiction} {classification.locality}"

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
                }
                for source in sources
            ],
            "evidence": [],
            "verification": [],
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
                lambda question: verify_claim(question, evidence),
                research_questions,
            )
        ]

    # -----------------------------------------------------
    # 9. Generate final user-facing response
    # -----------------------------------------------------

    final_response = generate_final_response(
        user_message=model_message,
        intake_data=intake_data,
        classification_data=classification_data,
        evidence=evidence,
        verification_results=verification_results,
        language=language,
    )

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
            }
            for source in sources
        ],

        "evidence": [
            item.model_dump()
            for item in evidence
        ],

        "verification": verification_results,

        "response": final_response.model_dump(),

        "status": "completed",
    }