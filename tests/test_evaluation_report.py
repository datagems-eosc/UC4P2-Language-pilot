"""StudentQuiz-compatible evaluation report with calculation elements."""

from src.evaluation.catalog import empty_measure_catalog
from src.evaluation.details import nlg_metrics_with_details
from src.evaluation.nlg import evaluate_against_ground_truth
from src.evaluation.report import build_evaluation_report


def test_catalog_matches_studentquiz_shape():
    catalog = empty_measure_catalog()
    assert catalog["schemaVersion"] == "1.0"
    assert catalog["evaluation"]["id"] == "uc4p2-language-pilot"
    assert catalog["measures"]
    measure = catalog["measures"][0]
    for key in (
        "id",
        "family",
        "label",
        "description",
        "definition",
        "valueType",
        "unit",
        "scale",
        "objective",
        "aggregation",
        "dimensions",
        "observations",
        "visualization",
        "provenance",
    ):
        assert key in measure
    assert measure["definition"]["formula"]
    assert measure["observations"] == []


def test_nlg_details_expose_elements():
    gold = "A city of Germany, the capital of Saxony."
    payload = nlg_metrics_with_details(gold + " [ref_1]", gold)
    assert payload["metrics"]["exact_match"] == 1.0
    detail = payload["details"]["token_f1"]
    assert detail["value"] == 1.0
    ids = {item["id"] for item in detail["elements"]}
    assert "overlap_count" in ids
    assert "precision" in ids
    assert "recall" in ids


def test_evaluation_report_has_per_metric_calculation():
    result = evaluate_against_ground_truth(
        "How is Dresden described?",
        "A city of Germany, the capital of Saxony.",
        query_id="1",
        llm_model="qwen3",
        judge_llm_model="glm-5.3-flash",
    )
    assert result["matched"] is True
    report = result["evaluation_report"]
    assert report["schemaVersion"] == "1.0"
    assert report["evaluation"]["projectId"] == "uc4p2_language_pilot"
    assert report["measures"]
    token_f1 = next(m for m in report["measures"] if m["id"] == "uc4p2.token_f1")
    obs = token_f1["observations"][0]
    assert obs["status"] == "ok"
    assert isinstance(obs["value"], float)
    assert obs["calculation"]["formula"]
    assert obs["calculation"]["elements"]
    assert obs["dimensions"]["query_id"] == "1"
    assert obs["dimensions"]["operator"] == "evaluate_answer"


def test_build_report_from_existing_nlg_blob():
    nlg = {
        "matched": True,
        "question_id": "1",
        "ground_truth": "capital of Saxony",
        "metrics": {},
        "llm_judge": {"available": False, "reason": "test"},
        "gold_source": "pilot2_benchmark_english.v2.json",
        "source": "local",
    }
    report = build_evaluation_report(
        question="How is Dresden described?",
        answer="capital of Saxony",
        nlg_evaluation=nlg,
        query_id="1",
        llm_model="qwen3",
    )
    exact = next(m for m in report["measures"] if m["id"] == "uc4p2.exact_match")
    assert exact["observations"][0]["value"] == 1.0
    elements = exact["observations"][0]["calculation"]["elements"]
    assert any(item["id"] == "hypothesis_normalized" for item in elements)


def test_attach_execution_measures_adds_system_family():
    from src.evaluation.report import attach_execution_measures

    base = build_evaluation_report(
        question="How is Dresden described?",
        answer="capital of Saxony",
        nlg_evaluation={
            "matched": True,
            "question_id": "1",
            "ground_truth": "capital of Saxony",
            "metrics": {},
            "llm_judge": {"available": False, "reason": "test"},
        },
        query_id="1",
        run_id="abc123deadbeef",
        llm_model="qwen3",
        judge_llm_model="glm-5.3-flash",
    )
    timings = [
        {"name": "route", "title": "Route", "outcome": "ok", "duration_s": 0.01, "duration_ms": 10},
        {
            "name": "evaluate_answer",
            "title": "Evaluate",
            "outcome": "ok",
            "duration_s": 1.25,
            "duration_ms": 1250,
        },
    ]
    report = attach_execution_measures(
        base,
        step_timings=timings,
        execution_time_s=1.26,
        evaluation_time_s=1.25,
        query_id="1",
        llm_model="qwen3",
        judge_llm_model="glm-5.3-flash",
        run_id="abc123deadbeef",
    )
    step_measure = next(m for m in report["measures"] if m["id"] == "uc4p2.execution_time")
    assert step_measure["family"] == "system"
    assert len(step_measure["observations"]) == 2
    assert step_measure["observations"][0]["dimensions"]["run_id"] == "abc123deadbeef"
    assert step_measure["observations"][0]["calculation"]["elements"]
    total = next(m for m in report["measures"] if m["id"] == "uc4p2.execution_time_total")
    assert total["observations"][0]["value"] == 1.26
    evaluation = next(m for m in report["measures"] if m["id"] == "uc4p2.evaluation_time")
    assert evaluation["observations"][0]["value"] == 1.25


def test_pipeline_trace_keeps_step_durations_and_run_identity():
    from src.app.runner import _attach_execution_timings, build_pipeline_trace

    events = [
        {"step": "route", "output": {"status": "ok"}, "duration_s": 0.02, "duration_ms": 20},
        {
            "step": "evaluate_answer",
            "output": {
                "status": "ok",
                "nlg_evaluation": {
                    "matched": False,
                    "metrics": {},
                    "evaluation_report": {
                        "schemaVersion": "1.0",
                        "evaluation": {"id": "uc4p2-language-pilot"},
                        "measures": [],
                    },
                },
            },
            "duration_s": 0.5,
            "duration_ms": 500,
        },
    ]
    trace = build_pipeline_trace(events)
    assert trace[0]["duration_s"] == 0.02
    assert trace[1]["duration_ms"] == 500.0
    payload = _attach_execution_timings(
        {
            "query_id": "1",
            "question": "How is Dresden described?",
            "run_id": "feedface00cafe",
            "llm_model": "qwen3",
            "judge_llm_model": "glm-5.3-flash",
            "pipeline": trace,
            "nlg_evaluation": events[1]["output"]["nlg_evaluation"],
        }
    )
    assert payload["execution_time_s"] == 0.52
    assert payload["evaluation_time_s"] == 0.5
    assert payload["run_id"] == "feedface00cafe"
    assert payload["execution"]["llm_model"] == "qwen3"
    assert payload["execution"]["judge_llm_model"] == "glm-5.3-flash"
    report = payload["nlg_evaluation"]["evaluation_report"]
    assert report["execution"]["run_id"] == "feedface00cafe"
    assert any(m["id"] == "uc4p2.execution_time" for m in report["measures"])
    assert payload["nlg_evaluation"]["run_id"] == "feedface00cafe"
