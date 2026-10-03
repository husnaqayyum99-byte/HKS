import json

from pydantic import BaseModel, Field

from app.services.ai_service import generate_response


class IntakeResult(BaseModel):
    problem_summary: str = "Not enough details were provided to summarize the matter."
    category: str = "unclear"
    location: str = "unknown"
    facts: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    urgency: str = "unclear"


def intake_case(user_message: str, language: str = "en") -> IntakeResult:
    language_instruction = {
        "en": "Write all text values in English.",
        "ur": "Write all text values in Urdu script.",
        "roman_urdu": "Write all text values in natural Pakistani Roman Urdu using Latin letters only. Do not use Urdu script.",
    }.get(language, "Write all text values in English.")

    prompt = f"""
You are the Intake Agent for Apna Wakeel, a Pakistan-focused legal
information and navigation system.

Your job is ONLY to understand and structure the user's situation.

Do NOT:
- give legal advice
- cite laws
- make legal conclusions
- claim that a particular law definitely applies
- invent facts
- invent sources

Identify:

1. problem_summary
2. category
3. location
4. facts
5. missing_information
6. urgency

Possible categories:
- traffic_accident
- property
- family
- employment
- criminal
- civil
- harassment
- fraud
- identity_documents
- government_services
- other
- unclear

Possible urgency values:
- emergency
- urgent
- normal
- unclear

Rules:
- {language_instruction}
- Treat earlier user messages and the current message as the case record; preserve material facts when the current message is only a follow-up.
- Earlier assistant messages are context for what has already been asked or discussed, not independent evidence of user facts. Use those facts only if the user stated or confirmed them.
- Attribute information extracted from a user-selected document to that document; do not silently treat it as independently verified.
- Only use information provided by the user or explicitly attributed to a user-selected document.
- Do not guess missing facts.
- If the location is not provided, use "unknown".
- If the category is unclear, use "unclear".
- If something important is missing, add it to missing_information.
- Return ONLY valid JSON.

Required JSON structure:

{{
    "problem_summary": "string",
    "category": "string",
    "location": "string",
    "facts": [],
    "missing_information": [],
    "urgency": "string"
}}

User's message:
{user_message}
"""

    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        return IntakeResult(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Intake Agent returned invalid data: {e}"
        )