import json
import re
from collections import defaultdict
from statistics import mean
from pathlib import Path


SCENARIO_FILE = Path(__file__).parents[2] / "tests" / "fixtures" / "legal_scenarios.json"
_STOP_WORDS = {
    "after", "about", "which", "where", "there", "their", "what", "when",
    "with", "from", "that", "this", "does", "have", "need", "should",
}


def load_scenarios() -> dict:
    with SCENARIO_FILE.open(encoding="utf-8") as fixture:
        return json.load(fixture)


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]{3,}", value.casefold())
        if token not in _STOP_WORDS
    }


def _matches(expected: str, actual_items: list[str], threshold: float = 0.4) -> bool:
    expected_tokens = _tokens(expected)
    if not expected_tokens:
        return False
    return any(
        len(expected_tokens & _tokens(actual)) / len(expected_tokens) >= threshold
        for actual in actual_items
    )


def evaluate_scenario(scenario: dict, result: dict) -> dict:
    intake = result.get("intake") or {}
    retained_text = " ".join([
        str(intake.get("problem_summary", "")),
        *[str(fact) for fact in (intake.get("facts") or [])],
    ])
    known_facts = scenario.get("known_facts", [])
    retained = sum(_matches(fact, [retained_text], threshold=0.5) for fact in known_facts)

    questions = (result.get("follow_up") or {}).get("questions") or result.get("follow_up_questions") or []
    repeated = sum(_matches(question, known_facts, threshold=0.5) for question in questions)
    blocking = scenario.get("blocking_questions", [])
    question_quality = (
        sum(_matches(expected, questions, threshold=0.35) for expected in blocking) / len(blocking)
        if blocking
        else float(not questions)
    )

    actual_research = (result.get("research") or {}).get("research_questions") or []
    expected_research = scenario.get("legal_research_questions", [])
    research_relevance = (
        sum(_matches(expected, actual_research, threshold=0.3) for expected in expected_research)
        / len(expected_research)
        if expected_research
        else 1.0
    )
    verification = result.get("verification") or []
    evidence_coverage = (
        sum(
            any(
                _matches(expected, [item.get("claim", "")], threshold=0.3)
                and bool(item.get("evidence_used"))
                for item in verification
            )
            for expected in expected_research
        ) / len(expected_research)
        if expected_research
        else 1.0
    )
    supported = [item for item in verification if item.get("status") == "supported"]
    unsupported_claim_rate = (
        sum(not item.get("evidence_used") for item in supported) / len(supported)
        if supported
        else 0.0
    )
    public_sources = result.get("sources") or []
    ui_evidence = float(bool(public_sources) and all(
        item.get("url") and item.get("excerpt") is not None and "claims" in item
        for item in public_sources
    ))
    expected_sources = scenario.get("expected_authoritative_sources", [])
    actual_sources = {
        str(item.get("name", item.get("source_name", ""))).casefold()
        for item in public_sources
        if item.get("url") and item.get("excerpt") is not None and "claims" in item
    }
    authority_source_coverage = (
        sum(expected.casefold() in actual_sources for expected in expected_sources)
        / len(expected_sources)
        if expected_sources
        else 1.0
    )

    legally_reviewed = scenario.get("review_status") == "reviewed_by_qualified_lawyer"
    response = result.get("response") or {}
    actual_procedure = (
        response.get("next_steps")
        or [item.get("title", "") for item in (result.get("actionPlan") or [])]
    )
    actual_documents = response.get("documents_needed") or result.get("documents", [])
    expected_procedure = scenario.get("expected_procedure_if_supported", [])
    expected_documents = scenario.get("expected_documents_if_supported", [])
    return {
        "context_retention": retained / len(known_facts) if known_facts else 1.0,
        "repeated_questions": repeated,
        "question_quality": question_quality,
        "research_relevance": research_relevance,
        "evidence_coverage": evidence_coverage,
        "unsupported_claim_rate": unsupported_claim_rate,
        "authority_source_coverage": authority_source_coverage,
        "procedure_coverage": (
            None if not legally_reviewed else
            sum(_matches(expected, actual_procedure, threshold=0.3) for expected in expected_procedure)
            / len(expected_procedure) if expected_procedure else 1.0
        ),
        "document_coverage": (
            None if not legally_reviewed else
            sum(_matches(expected, actual_documents, threshold=0.3) for expected in expected_documents)
            / len(expected_documents) if expected_documents else 1.0
        ),
        "ui_evidence": ui_evidence,
    }


def evaluate_benchmark(results_by_scenario: dict[str, dict]) -> dict:
    scenarios = load_scenarios()["scenarios"]
    per_scenario = {}
    metric_values: dict[str, list[float]] = defaultdict(list)
    for scenario in scenarios:
        result = results_by_scenario.get(scenario["id"])
        if result is None:
            per_scenario[scenario["id"]] = None
            continue
        metrics = evaluate_scenario(scenario, result)
        per_scenario[scenario["id"]] = metrics
        for metric, value in metrics.items():
            if value is not None:
                metric_values[metric].append(value)

    return {
        "scenario_count": len(scenarios),
        "evaluated_count": sum(value is not None for value in per_scenario.values()),
        "pending_legal_review_count": sum(
            scenario.get("review_status") != "reviewed_by_qualified_lawyer"
            for scenario in scenarios
        ),
        "metrics": {
            metric: mean(values) if values else None
            for metric, values in metric_values.items()
        },
        "per_scenario": per_scenario,
    }
