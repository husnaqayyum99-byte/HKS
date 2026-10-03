import json
import re
from typing import Literal

from groq import RateLimitError
from pydantic import BaseModel, Field

from app.services.ai_service import generate_response
from app.legal_sources.evidence import EvidenceItem


class VerificationResult(BaseModel):
    claim: str
    status: Literal["supported", "contradicted", "unresolved"] = "unresolved"
    supported: bool = False
    confidence: str = "unclear"
    reasoning: str = "The available response did not include a verification rationale."
    evidence_used: list[EvidenceItem] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)


def _verification_evidence(claim: str, evidence: list[EvidenceItem]) -> list[dict]:
    query_words = {
        word for word in re.findall(r"[a-z0-9]{4,}", claim.lower())
    }
    ranked = []

    for item in evidence:
        indexed_text = " ".join((item.source_title, item.citation or "", item.relevant_text))
        text_words = set(re.findall(r"[a-z0-9]{4,}", indexed_text.lower()))
        overlap = len(query_words & text_words)
        score = overlap * 10 + (item.retrieval_score or 0)
        if score:
            ranked.append((score, item))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    selected = []
    for _, item in ranked[:3]:
        evidence_data = item.model_dump()
        text = item.relevant_text
        section_numbers = re.findall(r"section\s+(\d+[A-Za-z]?)", item.citation or "", re.IGNORECASE)
        section_start = next(
            (
                match.start()
                for number in section_numbers
                for match in [re.search(rf"(?<!\w){re.escape(number)}\.", text)]
                if match
            ),
            None,
        )
        if section_start is not None:
            start = max(0, section_start - 120)
            evidence_data["relevant_text"] = text[start:start + 1800]
        else:
            evidence_data["relevant_text"] = text[:1800]
        selected.append(evidence_data)

    return selected


def verify_claim(
    claim: str,
    evidence: list[EvidenceItem],
    language: str = "en",
) -> VerificationResult:

    language_instruction = {
        "en": "Write reasoning and uncertainty in English.",
        "ur": "Write reasoning and uncertainty in Urdu script.",
        "roman_urdu": "Write reasoning and uncertainty in natural Pakistani Roman Urdu using Latin letters only; do not use Urdu script.",
    }.get(language, "Write reasoning and uncertainty in English.")
    fallback_text = {
        "en": {
            "unresolved": "The retrieved evidence does not establish an answer to this question.",
            "none": "No relevant retrieved evidence establishes this point.",
            "rate_limited": "Automatic verification was rate-limited and could not be completed.",
            "unverified": "This claim has not been automatically verified against the retrieved sources.",
            "unmatched": "No cited evidence could be matched to a retrieved source; this point remains unresolved.",
        },
        "ur": {
            "unresolved": "حاصل شدہ شواہد اس سوال کا جواب ثابت نہیں کرتے۔",
            "none": "متعلقہ حاصل شدہ شواہد اس نکتے کو ثابت نہیں کرتے۔",
            "rate_limited": "حدِ استعمال کے باعث خودکار تصدیق مکمل نہیں ہو سکی۔",
            "unverified": "اس دعوے کی حاصل شدہ ذرائع سے خودکار تصدیق نہیں ہوئی۔",
            "unmatched": "حوالہ شدہ شواہد کسی حاصل شدہ ذریعے سے نہیں ملے؛ یہ نکتہ غیر حل شدہ ہے۔",
        },
        "roman_urdu": {
            "unresolved": "Hasil shuda shawahid is sawal ka jawab sabit nahi karte.",
            "none": "Mutaliqa hasil shuda shawahid is nuqte ko sabit nahi karte.",
            "rate_limited": "Usage limit ki wajah se automatic tasdeeq mukammal nahi ho saki.",
            "unverified": "Is daaway ki hasil shuda sources se automatic tasdeeq nahi hui.",
            "unmatched": "Hawala diye gaye shawahid kisi hasil shuda source se nahi mile; yeh nuqta ghair hal shuda hai.",
        },
    }.get(language, {
        "unresolved": "The retrieved evidence does not establish an answer to this question.",
        "none": "No relevant retrieved evidence establishes this point.",
        "rate_limited": "Automatic verification was rate-limited and could not be completed.",
        "unverified": "This claim has not been automatically verified against the retrieved sources.",
        "unmatched": "No cited evidence could be matched to a retrieved source; this point remains unresolved.",
    })

    evidence_data = _verification_evidence(claim, evidence)
    if not evidence_data:
        return VerificationResult(
            claim=claim,
            status="unresolved",
            reasoning=fallback_text["unresolved"],
            uncertainty=[fallback_text["none"]],
        )

    prompt = f"""
You are the Verification Agent for Apna Wakeel.

Apna Wakeel is a Pakistan-focused legal information and navigation
system.

Your job is to determine whether a legal claim is actually supported
by the provided evidence.

IMPORTANT RULES:
0. {language_instruction}
1. Return status "supported" only when the supplied excerpts affirmatively establish the claim.
2. Return "contradicted" only when a reliable supplied excerpt affirmatively conflicts with the claim.
3. Return "unresolved" when evidence is absent, irrelevant, ambiguous, or silent. Silence never proves the opposite.
4. Cite only evidence included below. An unsupported model statement is not evidence.
5. "supported" is true only when status is supported; otherwise it is false.
6. Include matching evidence identifiers/URLs in evidence_used only for evidence that supports or contradicts the claim.
7. Explain what the evidence establishes and what it does not establish.

Return ONLY valid JSON.

Required structure:

{{
    "claim": "string",
    "status": "supported | contradicted | unresolved",
    "supported": true,
    "confidence": "high | medium | low | unclear",
    "reasoning": "string",
    "evidence_used": [],
    "uncertainty": []
}}

CLAIM:

{claim}

EVIDENCE:

{json.dumps(evidence_data, indent=2)}
"""

    try:
        raw_response = generate_response(prompt)
    except RateLimitError:
        return VerificationResult(
            claim=claim,
            status="unresolved",
            supported=False,
            confidence="unclear",
            reasoning=fallback_text["rate_limited"],
            uncertainty=[fallback_text["unverified"]],
        )

    try:
        data = json.loads(raw_response)
        data.setdefault("claim", claim)
        if data.get("status") not in {"supported", "contradicted", "unresolved"}:
            data["status"] = "supported" if data.get("supported") is True else "unresolved"
        returned_sources = data.get("evidence_used") or []
        if not isinstance(returned_sources, list):
            returned_sources = []
        matched_sources = []
        for returned_source in returned_sources:
            reference = (
                returned_source
                if isinstance(returned_source, str)
                else json.dumps(returned_source, ensure_ascii=False)
            ).lower()
            for item in evidence:
                trusted_references = (
                    item.source_name,
                    item.source_title,
                    item.source_url,
                    item.citation or "",
                )
                if any(value and value.lower() in reference for value in trusted_references):
                    if item not in matched_sources:
                        matched_sources.append(item)
        data["evidence_used"] = matched_sources
        if not matched_sources:
            data["status"] = "unresolved"
            data["supported"] = False
            data["confidence"] = "unclear"
            uncertainty = data.get("uncertainty")
            if not isinstance(uncertainty, list):
                uncertainty = []
            uncertainty.append(fallback_text["unmatched"])
            data["uncertainty"] = uncertainty
        else:
            data["supported"] = data["status"] == "supported"
        return VerificationResult(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Verification Agent returned invalid data: {e}"
        )