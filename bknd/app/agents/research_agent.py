import json

from pydantic import BaseModel, Field

from app.services.ai_service import generate_response
from app.legal_sources.evidence import EvidenceItem


class ResearchResult(BaseModel):
    research_questions: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    priority_jurisdictions: list[str] = Field(default_factory=list)
    evidence_needed: list[str] = Field(default_factory=list)
    laws_to_check: list[str] = Field(default_factory=list)


class EvidenceGapPlan(BaseModel):
    research_questions: list[str] = Field(default_factory=list)
    laws_to_check: list[str] = Field(default_factory=list)


def create_research_plan(
    intake_data: dict,
    classification_data: dict,
) -> ResearchResult:

    prompt = f"""
You are the Research Agent for Apna Wakeel.

Apna Wakeel is a Pakistan-focused legal information and navigation
system.

Your job is to create a research plan based on the user's intake
information and case classification.

You are NOT responsible for giving the final legal answer.

Do NOT:
- give legal advice
- make legal conclusions
- invent laws
- invent legal sources
- claim that a source says something unless actual source evidence
  has been provided
- fabricate URLs

Your job is to determine:

1. research_questions
2. source_types
3. priority_jurisdictions
4. evidence_needed
5. laws_to_check

Research questions should describe what needs to be verified.

Source types should identify appropriate authoritative sources,
for example:

- Pakistan federal legislation
- Khyber Pakhtunkhwa legislation
- KP government department
- district government
- police authority
- court judgment
- court rules
- NADRA
- revenue department
- local government
- official government procedure

Priority jurisdictions should identify the relevant geographic or
legal level.

Evidence_needed should describe the specific facts or legal
information required before a reliable answer can be produced.

Laws_to_check should contain only plausible statute or constitutional
document names to search in official government catalogs. Do not cite
sections or claim that a law applies; retrieval and verification happen later.

IMPORTANT:

Do not provide the final legal answer.

Do not invent a source.

Return ONLY valid JSON.

Required JSON structure:

{{
    "research_questions": [],
    "source_types": [],
    "priority_jurisdictions": [],
    "evidence_needed": [],
    "laws_to_check": []
}}

INTAKE INFORMATION:

{json.dumps(intake_data, indent=2)}

CLASSIFICATION INFORMATION:

{json.dumps(classification_data, indent=2)}
"""

    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        data["research_questions"] = data.get("research_questions", [])[:3]
        return ResearchResult(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Research Agent returned invalid data: {e}"
        )


def identify_evidence_gaps(
    user_message: str,
    intake_data: dict,
    classification_data: dict,
    research_plan: dict,
    evidence: list[EvidenceItem],
) -> EvidenceGapPlan:
    evidence_data = []
    for item in evidence[:12]:
        item_data = item.model_dump()
        item_data["relevant_text"] = item_data.get("relevant_text", "")[:1600]
        evidence_data.append(item_data)

    prompt = f"""
You are the Evidence Gap Research Agent for Apna Wakeel, a Pakistan-focused legal information system.

Your task is to compare the user's actual question with the initial research plan and retrieved evidence.
Identify material parts of the question that the evidence does not yet answer, then create targeted searches
for additional registered official sources. Focus on missing procedures, prerequisites, documents, deadlines,
authorities, and whether a requirement exists when those points are asked about.

IMPORTANT RULES:
1. Do not answer the user's legal question or make legal conclusions.
2. A source's silence is not evidence that a legal requirement does not exist. Never infer "not required" from omission.
3. Use only the user message, intake, classification, research plan, and evidence below.
4. Do not invent statutes or present guessed law names as fact. Suggest only plausible catalog search titles.
5. Return only questions needed to retrieve official evidence for material unanswered parts of the user's question.
6. Exclude questions already answered by the provided evidence or already covered by the initial plan.
7. Return at most four targeted research questions and four plausible law names. If all material issues are covered, return empty lists.
8. Return only valid JSON.

Required JSON structure:
{{
    "research_questions": [],
    "laws_to_check": []
}}

USER QUESTION:
{user_message}

INTAKE:
{json.dumps(intake_data, indent=2)}

CLASSIFICATION:
{json.dumps(classification_data, indent=2)}

INITIAL RESEARCH PLAN:
{json.dumps(research_plan, indent=2)}

RETRIEVED EVIDENCE:
{json.dumps(evidence_data, indent=2)}
"""
    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        data["research_questions"] = list(dict.fromkeys(data.get("research_questions", [])))[:4]
        data["laws_to_check"] = list(dict.fromkeys(data.get("laws_to_check", [])))[:4]
        return EvidenceGapPlan(**data)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"Evidence Gap Agent returned invalid data: {error}") from error