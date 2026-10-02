import json
from typing import Any

from pydantic import BaseModel, Field

from app.services.ai_service import generate_response
from app.legal_sources.evidence import EvidenceItem


class FinalResponse(BaseModel):
    answer: str = "The available information is not sufficient for a specific answer."
    next_steps: list[str] = Field(default_factory=list)
    documents_needed: list[str] = Field(default_factory=list)
    authorities: list[str] = Field(default_factory=list)
    sources: list[Any] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    disclaimer: str = ""


def generate_final_response(
    user_message: str,
    intake_data: dict,
    classification_data: dict,
    evidence: list[EvidenceItem],
    verification_results: list[dict],
    language: str = "en",
) -> FinalResponse:
    language_instruction = {
        "en": "Write the complete user-facing response in English.",
        "ur": "Write the complete user-facing response in Urdu script.",
        "roman_urdu": "Write the complete user-facing response in natural Pakistani Roman Urdu using Latin letters only. Do not use Urdu script.",
    }.get(language, "Write the complete user-facing response in English.")


    evidence_data = []
    for item in evidence[:12]:
        item_data = item.model_dump()
        item_data["relevant_text"] = item_data.get("relevant_text", "")[:1800]
        evidence_data.append(item_data)

    prompt = f"""
You are the Final Response Agent for Apna Wakeel.

Apna Wakeel is a Pakistan-focused legal information and navigation
system.

Your job is to produce a clear, simple and evidence-based response
for the user.

IMPORTANT RULES:

0. {language_instruction}
1. Use ONLY the evidence provided below for legal factual claims.
2. Do NOT invent laws, sections, procedures, authorities, documents,
   deadlines or penalties.
3. Do NOT use your general legal knowledge as evidence.
4. If a requested detail is absent, name the checked source set and
    state what those sources do not specify. Do not use a generic
    “I do not know” response.
5. Do NOT pretend that an unsupported claim is verified.
6. Clearly communicate uncertainty.
7. Do not guarantee a legal outcome.
8. Do not claim to be a lawyer or add generic first-person credentials disclaimers.
9. Use simple language and avoid unnecessary legal jargon.
10. Separate verified information from uncertainty.
11. Do not fabricate URLs or sources.
12. Only list authorities and sources that appear in the supplied
    evidence.
13. Cite legal propositions inline using statute and section labels
    explicitly present in the supplied evidence.
14. If evidence does not establish a provision or procedure, do not
    invent a citation.
15. Do not add generic “not a lawyer” or “not legal advice” boilerplate.
    Mention an under-review status only when the supplied evidence says so.
16. Begin the answer by briefly restating the user's situation using
    only facts in the user message and intake. Do not add or assume facts.
17. Then explain the relevant law or code in plain language and connect its verified rule to the stated facts.
    For each verified rule, identify its supporting source and explain how both relate to the user's stated facts.
    Cite the statute and section only when that citation appears in the supplied evidence.
18. If the evidence or missing facts do not establish whether a law
    applies, say what is uncertain and what information is needed instead
    of presenting a legal conclusion.
19. A source's silence does not establish that a requirement is absent.
    Never state that a procedure is not required unless the supplied
    evidence affirmatively establishes that conclusion. If focused research
    still does not answer the point, say that the retrieved sources do not
    establish whether it is required.

The response should help the user understand:
- what their issue appears to be
- how the retrieved law or code relates to the facts they shared
- what information is supported
- what they can do next
- what documents may be relevant
- which authority/source is relevant
- what remains uncertain

Return ONLY valid JSON.

Required structure:

{{
    "answer": "string",
    "next_steps": [],
    "documents_needed": [],
    "authorities": [],
    "sources": [],
    "uncertainty": [],
    "disclaimer": "string"
}}

USER MESSAGE:
{user_message}

INTAKE:
{json.dumps(intake_data, indent=2)}

CLASSIFICATION:
{json.dumps(classification_data, indent=2)}

EVIDENCE:
{json.dumps(evidence_data, indent=2)}

VERIFICATION RESULTS:
{json.dumps(verification_results, indent=2)}
"""

    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        return FinalResponse(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Final Response Agent returned invalid data: {e}"
        )