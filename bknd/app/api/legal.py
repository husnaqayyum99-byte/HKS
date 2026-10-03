import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from groq import RateLimitError
from pydantic import BaseModel, Field, field_validator

from app.agents.orchestrator import process_case
from app.legal_sources.source_registry import get_relevant_sources
from app.services.ai_service import GroqConfigurationError

router = APIRouter(prefix="/api", tags=["Public legal analysis"])
logger = logging.getLogger(__name__)


class PublicMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Conversation content cannot be empty")
        return value


class PublicAnalysisRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    language: Literal["en", "ur", "roman_urdu"] = "en"
    conversation_history: list[PublicMessage] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message content cannot be empty")
        return value


def _evidence_key(item: dict) -> tuple[str, str | None, str]:
    return (
        item.get("source_url", ""),
        item.get("citation"),
        item.get("source_title", ""),
    )


def _build_public_result(pipeline_result: dict) -> dict:
    intake = pipeline_result.get("intake") or {}
    classification = pipeline_result.get("classification") or {}
    response = pipeline_result.get("response") or {}
    claim_checks = list(pipeline_result.get("claim_verification") or [])
    known_claims = {check.get("claim") for check in claim_checks}
    claim_checks.extend(
        {
            "claim_type": "research_question",
            **check,
        }
        for check in pipeline_result.get("verification", [])
        if check.get("claim") not in known_claims
    )
    registered_sources = {
        source.name: source
        for source in get_relevant_sources(
            str(classification.get("jurisdiction") or ""),
            str(classification.get("legal_domain") or ""),
            str(classification.get("locality") or ""),
        )
    }

    claims_by_evidence: dict[tuple[str, str | None, str], list[dict]] = {}
    public_claims = []
    for check in claim_checks:
        used_items = [
            item for item in check.get("evidence_used", [])
            if isinstance(item, dict)
        ]
        public_claim = {
            "type": check.get("claim_type", "claim"),
            "claim": check.get("claim", ""),
            "status": check.get("status", "unresolved"),
            "uncertainty": check.get("uncertainty", []),
            "source_urls": list(dict.fromkeys(
                item.get("source_url")
                for item in used_items
                if item.get("source_url")
            )),
        }
        public_claims.append(public_claim)
        for item in used_items:
            claims_by_evidence.setdefault(_evidence_key(item), []).append({
                "type": public_claim["type"],
                "claim": public_claim["claim"],
                "status": public_claim["status"],
            })

    evidence = []
    seen_evidence = set()
    for item in pipeline_result.get("evidence", []):
        key = _evidence_key(item)
        if key in seen_evidence:
            continue
        seen_evidence.add(key)
        source = registered_sources.get(item.get("source_name"))
        related_claims = claims_by_evidence.get(key, [])
        evidence.append({
            "source_name": item.get("source_name", ""),
            "authority": source.authority if source else "",
            "source_url": item.get("source_url", ""),
            "source_title": item.get("source_title", ""),
            "jurisdiction": item.get("jurisdiction", ""),
            "source_type": item.get("source_type", ""),
            "source_priority": source.priority if source else 0,
            "source_active": source.active if source else False,
            "citation": item.get("citation"),
            "excerpt": item.get("relevant_text", ""),
            "official_status": item.get("official_status"),
            "retrieved_at": item.get("retrieved_at"),
            "verification_status": (
                related_claims[0]["status"] if related_claims
                else "unresolved"
            ),
            "claims": related_claims,
        })

    claims_by_type = {
        claim_type: {
            check.get("claim", ""): check
            for check in claim_checks
            if check.get("claim_type") == claim_type
        }
        for claim_type in ("next_step", "document", "authority")
    }

    def attach_claim(item: str, claim_type: str) -> dict:
        check = claims_by_type.get(claim_type, {}).get(item, {})
        return {
            "text": item,
            "status": check.get("status", "unresolved"),
            "source_urls": list(dict.fromkeys(
                source.get("source_url")
                for source in check.get("evidence_used", [])
                if isinstance(source, dict) and source.get("source_url")
            )),
        }

    follow_up = pipeline_result.get("follow_up") or {}
    status = pipeline_result.get("status", "evidence_unavailable")
    if status == "completed":
        check_statuses = [claim.get("status") for claim in public_claims]
        status = (
            "verified"
            if check_statuses and all(value == "supported" for value in check_statuses)
            else "partially_verified"
        )
    elif status == "evidence_unresolved":
        status = "unable_to_verify"

    return {
        "status": status,
        "understanding": intake.get("problem_summary", ""),
        "facts": intake.get("facts", []),
        "missing_information": intake.get("missing_information", []),
        "legal_area": classification.get("legal_domain", "unclear"),
        "jurisdiction": classification.get("jurisdiction", "Unknown"),
        "locality": classification.get("locality", "unknown"),
        "follow_up_questions": follow_up.get("questions", []),
        "answer": response.get("answer", ""),
        "authorities": [
            attach_claim(item, "authority")
            for item in response.get("authorities", [])
        ],
        "procedure": [
            attach_claim(item, "next_step")
            for item in response.get("next_steps", [])
        ],
        "timeline": [
            attach_claim(item, "next_step")
            for item in response.get("next_steps", [])
        ],
        "documents": [
            attach_claim(item, "document")
            for item in response.get("documents_needed", [])
        ],
        "next_steps": [
            attach_claim(item, "next_step")
            for item in response.get("next_steps", [])
        ],
        "uncertainty": response.get("uncertainty", []),
        "claims": public_claims,
        "evidence": evidence,
        "sources": [
            {
                "name": item["source_name"],
                "authority": item["authority"],
                "url": item["source_url"],
                "jurisdiction": item["jurisdiction"],
                "source_type": item["source_type"],
                "priority": item["source_priority"],
                "active": item["source_active"],
                "excerpt": item["excerpt"],
                "claims": item["claims"],
            }
            for item in evidence
        ],
        "disclaimer": response.get("disclaimer", ""),
    }


@router.post("/public-analysis")
def public_analysis(data: PublicAnalysisRequest):
    try:
        pipeline_result = process_case(
            data.content,
            conversation_history=[
                message.model_dump() for message in data.conversation_history
            ],
            language=data.language,
        )
    except GroqConfigurationError as error:
        logger.error("Public legal analysis configuration error: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from None
    except RateLimitError:
        logger.exception("Public legal analysis was rate-limited")
        raise HTTPException(
            status_code=429,
            detail="The AI service has reached its current usage limit. Please try again later.",
        ) from None
    except Exception:
        logger.exception("Public legal analysis pipeline failed")
        raise HTTPException(
            status_code=503,
            detail="The legal analysis service is temporarily unavailable. Please try again.",
        ) from None

    return _build_public_result(pipeline_result)
