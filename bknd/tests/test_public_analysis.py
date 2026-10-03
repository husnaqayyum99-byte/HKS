from fastapi.testclient import TestClient

from app.api import legal
from app.main import app
from app.services.ai_service import GroqConfigurationError


def _evidence():
    return {
        "source_name": "Pakistan Code",
        "source_url": "https://pakistancode.gov.pk/english/law",
        "source_title": "Tenancy law information",
        "jurisdiction": "Federal",
        "source_type": "legislation",
        "relevant_text": "Retrieved official legislation excerpt.",
        "citation": "Relevant statutory provision",
        "retrieved_at": "2026-10-03T12:00:00+00:00",
    }


def test_public_analysis_uses_shared_pipeline_and_maps_claims_to_evidence(monkeypatch):
    evidence = _evidence()
    called = {}

    def process_case(content, conversation_history, language):
        called.update({
            "content": content,
            "conversation_history": conversation_history,
            "language": language,
        })
        return {
            "status": "completed",
            "intake": {
                "problem_summary": "A tenant reports a lockout.",
                "facts": ["rented house"],
                "incident_location": "Chitral",
                "incident_type": "road accident",
                "vehicle_damage": "door damage",
                "responsibility_dispute": True,
                "compensation_dispute": False,
            },
            "classification": {
                "legal_domain": "tenancy",
                "legal_subtype": "vehicle_damage",
                "jurisdiction": "Pakistan",
                "locality": "unknown",
            },
            "follow_up": {
                "questions": ["Which documents do you have?"],
                "conversational_message": "Which documents do you have?",
            },
            "response": {
                "answer": "The supplied official evidence supports this limited point.",
                "authorities": ["Relevant authority"],
                "next_steps": ["Keep a copy of the rental agreement."],
                "documents_needed": ["Rental agreement"],
                "uncertainty": ["The retrieved evidence does not establish local procedure."],
                "disclaimer": "General information only.",
            },
            "evidence": [evidence],
            "claim_verification": [
                {
                    "claim_type": "next_step",
                    "claim": "Keep a copy of the rental agreement.",
                    "status": "supported",
                    "reasoning": "The retrieved excerpt supports this preparation step.",
                    "uncertainty": [],
                    "evidence_used": [evidence],
                },
                {
                    "claim_type": "document",
                    "claim": "Rental agreement",
                    "status": "supported",
                    "reasoning": "The retrieved excerpt identifies this record.",
                    "uncertainty": [],
                    "evidence_used": [evidence],
                },
                {
                    "claim_type": "authority",
                    "claim": "Relevant authority",
                    "status": "supported",
                    "reasoning": "The source identifies the authority.",
                    "uncertainty": [],
                    "evidence_used": [evidence],
                },
            ],
        }

    monkeypatch.setattr(legal, "process_case", process_case)
    response = TestClient(app).post("/api/public-analysis", json={
        "content": "What documents should I keep?",
        "language": "roman_urdu",
        "conversation_history": [{"role": "user", "content": "My landlord locked me out."}],
    })

    assert response.status_code == 200
    result = response.json()
    assert called == {
        "content": "What documents should I keep?",
        "conversation_history": [{"role": "user", "content": "My landlord locked me out."}],
        "language": "roman_urdu",
    }
    assert result["legal_area"] == "tenancy"
    assert result["legal_subtype"] == "vehicle_damage"
    assert result["incident_location"] == "Chitral"
    assert result["incident_type"] == "road accident"
    assert result["vehicle_damage"] == "door damage"
    assert result["responsibility_dispute"] is True
    assert result["compensation_dispute"] is False
    assert result["jurisdiction"] == "Pakistan"
    assert result["status"] == "verified"
    assert result["follow_up_questions"] == ["Which documents do you have?"]
    assert "conversational_message" not in result
    assert result["timeline"][0]["status"] == "supported"
    assert result["documents"][0]["source_urls"] == [evidence["source_url"]]
    assert result["evidence"][0]["claims"][0]["claim"] == "Keep a copy of the rental agreement."
    assert result["sources"][0]["authority"] == "Ministry of Law and Justice, Government of Pakistan"
    assert result["sources"][0]["active"] is True
    assert result["sources"][0]["priority"] == 100
    assert result["evidence"][0]["retrieved_at"] == "2026-10-03T12:00:00+00:00"
    assert result["evidence"][0]["freshness_status"] == "not_assessed"
    assert "reasoning" not in result["claims"][0]


def test_public_analysis_preserves_unresolved_status_when_no_evidence_exists(monkeypatch):
    monkeypatch.setattr(legal, "process_case", lambda *args, **kwargs: {
        "status": "evidence_unavailable",
        "intake": {"problem_summary": "A legal matter."},
        "classification": {"legal_domain": "unclear", "jurisdiction": "Unknown"},
        "response": {},
        "evidence": [],
        "claim_verification": [],
    })

    response = TestClient(app).post("/api/public-analysis", json={
        "content": "What should I do?",
    })

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "evidence_unavailable"
    assert result["evidence"] == []
    assert result["sources"] == []
    assert result["timeline"] == []


def test_public_analysis_keeps_research_question_to_evidence_links(monkeypatch):
    evidence = _evidence()
    monkeypatch.setattr(legal, "process_case", lambda *args, **kwargs: {
        "status": "evidence_unresolved",
        "intake": {"problem_summary": "A legal matter."},
        "classification": {"legal_domain": "tenancy", "jurisdiction": "Pakistan"},
        "verification": [{
            "claim": "Which authority handles this procedure?",
            "status": "unresolved",
            "reasoning": "The excerpt does not establish the competent authority.",
            "evidence_used": [evidence],
        }],
        "response": {"answer": "The available official evidence does not establish a verified answer."},
        "evidence": [evidence],
    })

    response = TestClient(app).post("/api/public-analysis", json={
        "content": "Who handles this procedure?",
    })

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unable_to_verify"
    assert result["evidence"][0]["claims"] == [{
        "type": "research_question",
        "claim": "Which authority handles this procedure?",
        "status": "unresolved",
    }]


def test_public_analysis_returns_safe_configuration_error_without_faking_guidance(monkeypatch):
    def fail_for_missing_configuration(*_args, **_kwargs):
        raise GroqConfigurationError("GROQ_API_KEY is not configured.")

    monkeypatch.setattr(legal, "process_case", fail_for_missing_configuration)

    response = TestClient(app).post("/api/public-analysis", json={
        "content": "What can I do?",
    })

    assert response.status_code == 503
    assert response.json()["detail"] == "GROQ_API_KEY is not configured."


def test_public_analysis_rejects_blank_or_oversized_requests():
    client = TestClient(app)

    assert client.post("/api/public-analysis", json={"content": "  "}).status_code == 422
    assert client.post("/api/public-analysis", json={"content": "x" * 8001}).status_code == 422


def test_public_analysis_route_is_post_only():
    response = TestClient(app).get("/api/public-analysis")

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
