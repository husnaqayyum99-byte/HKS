import json
import re

from pydantic import BaseModel, Field

from app.services.ai_service import generate_response

MAX_FOLLOW_UP_QUESTIONS = 8


class FollowUpResult(BaseModel):
    needs_follow_up: bool = False
    questions: list[str] = Field(default_factory=list)
    reason: str = ""
    conversational_message: str = ""


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _review_question_coverage(
    questions: list[str],
    conversational_message: str,
    user_message: str,
    intake_data: dict,
    classification_data: dict,
    history_text: str,
    language_instruction: str,
) -> tuple[list[str], str]:
    prompt = f"""
You are the final sufficiency check before legal research. First decide
whether the known facts are enough to begin useful, evidence-grounded
research. Do not optimize for collecting more information.

Review every candidate against the COMPLETE conversation, including prior
assistant questions and all user replies, the current user message, and the
structured intake/classification. Combine facts across user turns. Preserve
explicit unknowns, forgotten details, negative answers, absent dates/documents,
and statements such as "that's all the information I have" as valid case
facts. Assistant messages may show what was asked, but are not evidence that
the user stated or confirmed a fact.

For each candidate, return one question_checks entry with its zero-based
question_index and one status:
- answered: the user supplied the requested fact, including with different
  wording.
- unknown: the user said they do not know, remember, have, or that no such
  date/answer exists. This is a valid answer; do not ask again.
- approximate_sufficient: the user provided an approximate value and exact
  precision is not genuinely necessary for a material legal research
  decision. Do not ask again.
- unanswered: the conversation contains no answer to this genuinely material
  question, and the fact can materially change the relevant legal route,
  authority, procedure, research, or safe next step.
- precision_material: the user gave only an approximate answer, and the
  exact detail is genuinely necessary to determine the legal area,
  jurisdiction, source retrieval, or an immediate safe next step. Do not
  rely on general legal knowledge or speculate about a possible deadline.
  Include the specific reason. The conversational wording must explain why
  precision would help and explicitly make clear that "I don't know" is okay.

Apply this test to EVERY candidate: would its answer materially change the
legal area, jurisdiction, relevant authority or procedure, evidence/documents
to preserve, or immediate next step? If not, mark it answered/unknown/
approximate_sufficient as appropriate and do not ask. Ask only the minimum
necessary details; several material gaps may be asked together.

Never request a person's full name, phone number, email, or private address
for general legal analysis. Do not ask whether evidence exists if the user
already mentioned relevant messages, receipts, agreements, photos, or other
records. A negative response such as "there was no specific date" or "I
haven't complained" is an answer, not a missing fact. If the user says this
is all the information they have, set research_ready to true unless a fact
is genuinely indispensable to identify the legal area, jurisdiction, or a
safe research path.

Prefer proceeding with uncertainty noted over another question when research
can begin safely. The exact move-out date, optional personal identifiers,
and additional evidence should not block research when an approximate
timeline, location, and existing records are known.

Then write conversational_message as the complete, natural user-facing
message containing ONLY the questions whose status is unanswered or
precision_material. Briefly acknowledge relevant known facts without
repeating the whole case. Do not use headings, numbered labels, scripted
phrases, or add facts. If no questions are approved, return an empty string.
If research_ready is true, return no approved questions and an empty
conversational_message. Otherwise ask only the approved questions. Use the
requested language: {language_instruction}

Return only valid JSON in this shape:
{{
  "research_ready": false,
  "question_checks": [
    {{"question_index": 0, "status": "unanswered", "reason": "This material fact is not in the conversation."}}
  ],
  "conversational_message": "A natural question that explains why this material fact matters."
}}

COMPLETE PRIOR CONVERSATION:
{history_text or "No earlier messages."}

CURRENT USER MESSAGE:
{user_message}

INTAKE:
{json.dumps(intake_data, indent=2)}

CLASSIFICATION:
{json.dumps(classification_data, indent=2)}

CANDIDATE QUESTIONS:
{json.dumps(questions, ensure_ascii=False, indent=2)}

DRAFT CONVERSATIONAL MESSAGE (for context only; do not preserve questions
that your coverage review rejects):
{conversational_message}
"""
    raw_response = generate_response(prompt)
    try:
        data = json.loads(raw_response)
        research_ready = data.get("research_ready")
        checks = data.get("question_checks")
        reviewed_message = data.get("conversational_message")
        if (
            not isinstance(research_ready, bool)
            or not isinstance(checks, list)
            or not isinstance(reviewed_message, str)
        ):
            raise ValueError("Question coverage review returned an invalid structure.")

        valid_statuses = {
            "answered",
            "unknown",
            "approximate_sufficient",
            "unanswered",
            "precision_material",
        }
        checks_by_index = {}
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError("Question coverage entries must be objects.")
            index = check.get("question_index")
            status = check.get("status")
            reason = check.get("reason")
            if (
                not isinstance(index, int)
                or isinstance(index, bool)
                or index < 0
                or index >= len(questions)
                or status not in valid_statuses
                or not isinstance(reason, str)
                or not reason.strip()
                or index in checks_by_index
            ):
                raise ValueError("Question coverage review returned an invalid decision.")
            checks_by_index[index] = check

        if set(checks_by_index) != set(range(len(questions))):
            raise ValueError("Question coverage review must assess every candidate question.")

        if research_ready:
            return [], ""

        approved = [
            question
            for index, question in enumerate(questions)
            if checks_by_index[index]["status"] in {"unanswered", "precision_material"}
        ]
        if not approved:
            return [], ""
        return approved, reviewed_message.strip()
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"Question coverage review returned invalid data: {error}") from error


def generate_follow_up_questions(
    user_message: str,
    intake_data: dict,
    classification_data: dict,
    conversation_history: list[dict] | None = None,
    language: str = "en",
) -> FollowUpResult:
    history = conversation_history or []
    history_text = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in history
    )
    language_instruction = {
        "en": "Write every question and the reason in English.",
        "ur": "Write every question and the reason in Urdu script.",
        "roman_urdu": "Write every question and the reason in natural Pakistani Roman Urdu using Latin letters only. Do not use Urdu script.",
    }.get(language, "Write every question and the reason in English.")

    prompt = f"""
You are the Follow-up Agent for Apna Wakeel.

Apna Wakeel is a Pakistan-focused legal information and navigation
system.

Your job is to determine whether important information is missing
from the user's case before the system continues with legal
information research.

IMPORTANT RULES:

0. {language_instruction}
1. Use ONLY the information provided by the user and the structured
   intake/classification data.
2. Do NOT invent facts.
3. Do NOT give legal advice.
4. Do NOT cite laws.
5. Do NOT make legal conclusions.
6. Do NOT ask questions about information that is already provided.
7. Ask only questions that are relevant to understanding the case.
8. Keep questions simple and easy for a normal user to understand.
9. Identify only missing facts that are genuinely necessary to understand
   the legal route or choose a safe next step. Ask for them together in one concise batch.
   Do not ask more than {MAX_FOLLOW_UP_QUESTIONS} questions.
10. First decide whether there is enough information to begin useful,
    evidence-grounded research. Do not try to complete a checklist. Ask only
    a missing fact whose answer would materially change the legal area,
    jurisdiction, appropriate authority/procedure, evidence to preserve, or
    immediate next step. Do not ask details merely because they could be
    useful.
    If questions are needed, write conversational_message as the complete
    user-facing reply: briefly acknowledge relevant facts the user actually
    shared, then ask the questions naturally together. Keep it concise and
    professional. Do not use headings, numbered labels, form language, or
    stock transitions. Include every question from questions exactly once.
    Do not repeat the whole case summary.
11. If enough information is available to begin reliable research, set needs_follow_up to false
    and return an empty questions list and conversational_message.
12. Do not repeat questions already asked or ask for facts already supplied or answered anywhere in the complete conversation or structured case record, including paraphrases and answers spread across turns.
13. Use the complete conversation and structured intake/classification as the current case record; do not treat a follow-up as a separate case. Treat explicit unknowns, "I don't remember", "there was no specific date", missing documents, and "that's all the information I have" as valid facts, not failed answers.
14. If the user says they do not know, are unsure, or do not have something, accept that as an answer. Do not ask it again; proceed with the limits clear unless that unknown makes it impossible to identify a safe next step.
15. After the user answers a batch, perform a final sufficiency check. If research can begin safely, return no questions and proceed even if optional details remain unknown.
16. Research using known information by default. If a detail is not essential to begin research, record it as unknown rather than asking.
17. If the user is asking what to do next, provide the best available
    guidance instead of blocking on more details.
18. Return ONLY valid JSON.

Examples of useful missing information may include:
- location
- date or approximate time
- people involved
- injuries
- documents available
- whether a complaint/report was already made
- whether there is a disagreement or dispute
- what outcome the user is seeking

Do NOT automatically ask for all of these.
Only ask questions that are relevant to this particular case.
Never request personal identifiers such as a landlord's full name, phone
number, email, or private address merely to analyze a dispute. Do not request
more evidence of a type the user already said they have.

Required JSON structure:

{{
    "needs_follow_up": true,
    "conversational_message": "A natural, concise reply for the user when clarification is needed; otherwise an empty string.",
    "questions": [
        "Each concise, case-specific question needed in this batch"
    ],
    "reason": "Brief explanation distinguishing required facts from useful details."
}}

USER MESSAGE:
{user_message}

RECENT CONVERSATION:
{history_text or "No earlier messages."}

INTAKE INFORMATION:
{json.dumps(intake_data, indent=2)}

CLASSIFICATION INFORMATION:
{json.dumps(classification_data, indent=2)}
"""

    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        questions = data.get("questions") or []
        if not isinstance(questions, list):
            raise ValueError("Follow-up Agent questions must be a list.")
        conversational_message = data.get("conversational_message", "")
        if not isinstance(conversational_message, str):
            raise ValueError("Follow-up Agent conversational message must be a string.")
        deduplicated = []
        seen_questions = set()
        for question in questions:
            if not isinstance(question, str) or not question.strip():
                continue
            clean_question = question.strip()
            normalized_question = _normalized_text(clean_question)
            if not normalized_question or normalized_question in seen_questions:
                continue
            seen_questions.add(normalized_question)
            deduplicated.append(clean_question)
            if len(deduplicated) == MAX_FOLLOW_UP_QUESTIONS:
                break

        if deduplicated:
            deduplicated, conversational_message = _review_question_coverage(
                questions=deduplicated,
                conversational_message=conversational_message.strip(),
                user_message=user_message,
                intake_data=intake_data,
                classification_data=classification_data,
                history_text=history_text,
                language_instruction=language_instruction,
            )

        data["questions"] = deduplicated
        data["needs_follow_up"] = bool(data["questions"])
        data["conversational_message"] = (
            conversational_message.strip() if data["questions"] else ""
        )
        return FollowUpResult(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Follow-up Agent returned invalid data: {e}"
        )