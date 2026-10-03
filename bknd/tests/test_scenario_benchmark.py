from app.evaluation.legal_scenarios import evaluate_benchmark, evaluate_scenario, load_scenarios


def test_benchmark_contains_twenty_structured_scenarios_across_initial_scope():
    benchmark = load_scenarios()
    scenarios = benchmark["scenarios"]

    assert len(scenarios) == 20
    assert {scenario["category"] for scenario in scenarios} == {
        "identity_cnic",
        "property_inheritance",
        "tenancy",
        "employment",
        "police_reporting",
    }
    for scenario in scenarios:
        assert scenario["original_situation"]
        assert scenario["known_facts"]
        assert "missing_facts" in scenario
        assert "blocking_questions" in scenario
        assert scenario["legal_research_questions"]
        assert scenario["expected_authoritative_sources"]
        assert "expected_procedure_if_supported" in scenario
        assert "expected_documents_if_supported" in scenario
        assert scenario["must_not_claim_without_evidence"]
        assert scenario["review_status"] == "pending_qualified_legal_review"


def test_benchmark_metrics_report_context_questions_research_and_evidence():
    scenario = {
        "known_facts": ["brother died", "Chitral", "agricultural land", "three heirs"],
        "blocking_questions": [],
        "legal_research_questions": ["Which authority records inherited agricultural land?"],
        "expected_authoritative_sources": ["Revenue and Estate Department"],
        "expected_procedure_if_supported": [],
        "expected_documents_if_supported": [],
        "review_status": "pending_qualified_legal_review",
    }
    result = {
        "intake": {
            "problem_summary": "The user's brother died in Chitral, leaving agricultural land for three heirs.",
            "facts": [],
        },
        "follow_up": {"questions": []},
        "research": {"research_questions": ["Which authority records inherited agricultural land?"]},
        "verification": [{
            "claim": "Which authority records inherited agricultural land?",
            "status": "supported",
            "evidence_used": [{"source_url": "https://revenue.kp.gov.pk/"}],
        }],
        "sources": [{
            "name": "Revenue and Estate Department",
            "url": "https://revenue.kp.gov.pk/",
            "excerpt": "Revenue department information.",
            "claims": [],
        }],
    }

    metrics = evaluate_scenario(scenario, result)

    assert metrics["context_retention"] == 1.0
    assert metrics["repeated_questions"] == 0
    assert metrics["question_quality"] == 1.0
    assert metrics["research_relevance"] == 1.0
    assert metrics["evidence_coverage"] == 1.0
    assert metrics["unsupported_claim_rate"] == 0.0
    assert metrics["authority_source_coverage"] == 1.0
    assert metrics["procedure_coverage"] is None
    assert metrics["document_coverage"] is None
    assert metrics["ui_evidence"] == 1.0


def test_benchmark_aggregates_only_available_results_and_marks_review_gap():
    report = evaluate_benchmark({})

    assert report["scenario_count"] == 20
    assert report["evaluated_count"] == 0
    assert report["pending_legal_review_count"] == 20
    assert report["metrics"] == {}
    assert all(value is None for value in report["per_scenario"].values())
