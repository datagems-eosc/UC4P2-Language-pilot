"""Build a StudentQuiz-compatible evaluation document for one pipeline run."""

from __future__ import annotations

from typing import Any

from src.evaluation.catalog import (
    EVALUATION_META,
    MEASURE_SPECS,
    SCHEMA_VERSION,
    SYSTEM_MEASURE_SPECS,
    _dim,
    _measure_from_spec,
)
from src.evaluation.details import judge_details, nlg_metrics_with_details
from src.evaluation.nlg import strip_citation_marks


def build_evaluation_report(
    *,
    question: str,
    answer: str,
    nlg_evaluation: dict[str, Any],
    query_id: str = "",
    decompose_mode: str = "",
    llm_model: str = "",
    judge_llm_model: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    """Return ``schemaVersion`` / ``evaluation`` / ``measures`` shaped like StudentQuiz.json.

    Each measure observation includes ``calculation`` with formula + elements (inputs
    and intermediate values used to produce ``value``).
    """
    matched = bool(nlg_evaluation.get("matched"))
    gold = str(nlg_evaluation.get("ground_truth") or "")
    cleaned = strip_citation_marks(answer)
    flat_metrics = dict(nlg_evaluation.get("metrics") or {})
    detail_map: dict[str, dict[str, Any]] = {}

    if matched and gold:
        computed = nlg_metrics_with_details(answer, gold)
        # Prefer freshly computed details; keep remote flat metrics if present and equal.
        detail_map.update(computed["details"])
        if not flat_metrics:
            flat_metrics = dict(computed["metrics"])
        else:
            # Ensure every catalog NLG key exists even if remote omitted some.
            for key, value in computed["metrics"].items():
                flat_metrics.setdefault(key, value)

    judge = dict(nlg_evaluation.get("llm_judge") or {})
    detail_map.update(
        judge_details(judge, question=question, gold=gold, answer=cleaned)
    )

    dimensions = {
        "query_id": str(nlg_evaluation.get("question_id") or query_id or ""),
        "operator": "evaluate_answer",
        "gold_source": str(
            nlg_evaluation.get("gold_source")
            or nlg_evaluation.get("source")
            or ("unmatched" if not matched else "local")
        ),
        "llm_model": llm_model or "",
        "judge_llm_model": judge_llm_model or "",
        "decompose_mode": decompose_mode or "",
        "match": str(nlg_evaluation.get("match") or ""),
        "run_id": run_id or "",
    }

    measures: list[dict[str, Any]] = []
    for spec in MEASURE_SPECS:
        metric_key = str(spec["metric_key"])
        calc = detail_map.get(metric_key) or {}
        if metric_key.startswith("judge."):
            field = metric_key.split(".", 1)[1]
            value = judge.get(field) if judge.get("available") else None
            status = "ok" if judge.get("available") and value is not None else "missing"
        else:
            value = flat_metrics.get(metric_key)
            if value is None and calc.get("value") is not None:
                value = calc["value"]
            if not matched:
                status = "missing"
            elif value is None:
                status = "missing"
            else:
                status = "ok"

        observation: dict[str, Any] = {
            "id": f"{spec['id'].split('.')[-1]}-{dimensions['query_id'] or 'run'}",
            "value": value,
            "dimensions": {
                "query_id": dimensions["query_id"],
                "operator": dimensions["operator"],
                "gold_source": dimensions["gold_source"],
                "llm_model": dimensions["llm_model"],
            },
            "status": status,
        }
        if calc:
            observation["calculation"] = {
                "formula": calc.get("formula") or spec["definition"].get("formula"),
                "elements": list(calc.get("elements") or []),
            }
        else:
            observation["calculation"] = {
                "formula": spec["definition"].get("formula"),
                "elements": [],
                "note": "Calculation elements unavailable for this observation.",
            }

        measures.append(
            {
                "id": spec["id"],
                "family": spec["family"],
                "label": spec["label"],
                "description": spec["description"],
                "definition": dict(spec["definition"]),
                "valueType": spec["valueType"],
                "unit": dict(spec["unit"]),
                "scale": spec["scale"],
                "objective": spec["objective"],
                "aggregation": dict(spec["aggregation"]),
                "dimensions": _dim(),
                "observations": [observation],
                "visualization": dict(spec["visualization"]),
                "provenance": {
                    "sourceFile": (
                        "src/evaluation/judge.py"
                        if metric_key.startswith("judge.")
                        else "src/evaluation/nlg.py"
                    ),
                    "sourceMeasure": metric_key,
                    "gold_question": nlg_evaluation.get("gold_question") or question,
                    "ground_truth": gold,
                    "synthesized_answer": answer,
                    "summary": nlg_evaluation.get("summary") or "",
                },
            }
        )

    evaluation = dict(EVALUATION_META)
    evaluation = {
        **evaluation,
        "provenance": {
            **dict(EVALUATION_META.get("provenance") or {}),
            "run": {
                "query_id": dimensions["query_id"],
                "question": question,
                "matched": matched,
                "gold_source": dimensions["gold_source"],
                "decompose_mode": dimensions["decompose_mode"],
                "llm_model": dimensions["llm_model"],
                "judge_llm_model": dimensions["judge_llm_model"],
                "run_id": dimensions["run_id"],
                "source": nlg_evaluation.get("source") or "local",
            },
        },
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "evaluation": evaluation,
        "measures": measures,
    }


def attach_execution_measures(
    report: dict[str, Any],
    *,
    step_timings: list[dict[str, Any]],
    execution_time_s: float | None,
    evaluation_time_s: float | None,
    query_id: str = "",
    llm_model: str = "",
) -> dict[str, Any]:
    """Replace/add system execution-time measures on a StudentQuiz-shaped report."""
    updated = dict(report)
    measures = [
        measure
        for measure in list(updated.get("measures") or [])
        if not str(measure.get("id") or "").startswith("uc4p2.execution_time")
        and str(measure.get("id") or "") != "uc4p2.evaluation_time"
    ]
    by_id = {spec["id"]: spec for spec in SYSTEM_MEASURE_SPECS}

    step_spec = by_id["uc4p2.execution_time"]
    step_measure = _measure_from_spec(step_spec)
    step_observations: list[dict[str, Any]] = []
    for item in step_timings:
        name = str(item.get("name") or "step")
        duration = item.get("duration_s")
        if duration is None:
            continue
        duration_s = round(float(duration), 4)
        duration_ms = item.get("duration_ms")
        if duration_ms is None:
            duration_ms = round(duration_s * 1000, 1)
        step_observations.append(
            {
                "id": f"execution_time-{name}-{query_id or 'run'}",
                "value": duration_s,
                "dimensions": {
                    "operator": name,
                    "query_id": query_id or "",
                    "llm_model": llm_model or "",
                },
                "status": "ok",
                "calculation": {
                    "formula": step_spec["definition"]["formula"],
                    "elements": [
                        {"id": "operator", "label": "Pipeline step", "value": name},
                        {
                            "id": "title",
                            "label": "Step title",
                            "value": item.get("title") or name,
                        },
                        {
                            "id": "outcome",
                            "label": "Step outcome",
                            "value": item.get("outcome"),
                        },
                        {
                            "id": "duration_s",
                            "label": "Wall-clock duration",
                            "value": duration_s,
                            "unit": "s",
                        },
                        {
                            "id": "duration_ms",
                            "label": "Wall-clock duration",
                            "value": duration_ms,
                            "unit": "ms",
                        },
                    ],
                },
            }
        )
    step_measure["observations"] = step_observations
    measures.append(step_measure)

    total_spec = by_id["uc4p2.execution_time_total"]
    total_measure = _measure_from_spec(total_spec)
    if execution_time_s is not None:
        total_measure["observations"] = [
            {
                "id": f"execution_time_total-{query_id or 'run'}",
                "value": round(float(execution_time_s), 4),
                "dimensions": {
                    "query_id": query_id or "",
                    "operator": "pipeline",
                    "llm_model": llm_model or "",
                },
                "status": "ok",
                "calculation": {
                    "formula": total_spec["definition"]["formula"],
                    "elements": [
                        {
                            "id": "step_count",
                            "label": "Timed steps",
                            "value": len(step_timings),
                        },
                        {
                            "id": "step_durations_s",
                            "label": "Per-step durations (s)",
                            "value": {
                                str(item.get("name")): item.get("duration_s")
                                for item in step_timings
                            },
                        },
                        {
                            "id": "execution_time_s",
                            "label": "Sum of step durations",
                            "value": round(float(execution_time_s), 4),
                            "unit": "s",
                        },
                    ],
                },
            }
        ]
    measures.append(total_measure)

    eval_spec = by_id["uc4p2.evaluation_time"]
    eval_measure = _measure_from_spec(eval_spec)
    if evaluation_time_s is not None:
        eval_measure["observations"] = [
            {
                "id": f"evaluation_time-{query_id or 'run'}",
                "value": round(float(evaluation_time_s), 4),
                "dimensions": {
                    "query_id": query_id or "",
                    "operator": "evaluate_answer",
                    "llm_model": llm_model or "",
                },
                "status": "ok",
                "calculation": {
                    "formula": eval_spec["definition"]["formula"],
                    "elements": [
                        {
                            "id": "operator",
                            "label": "Pipeline step",
                            "value": "evaluate_answer",
                        },
                        {
                            "id": "duration_s",
                            "label": "Evaluation wall-clock duration",
                            "value": round(float(evaluation_time_s), 4),
                            "unit": "s",
                        },
                        {
                            "id": "includes",
                            "label": "Included work",
                            "value": "NLG metrics + optional LLM-as-judge",
                        },
                    ],
                },
            }
        ]
    else:
        eval_measure["observations"] = [
            {
                "id": f"evaluation_time-{query_id or 'run'}",
                "value": None,
                "dimensions": {
                    "query_id": query_id or "",
                    "operator": "evaluate_answer",
                    "llm_model": llm_model or "",
                },
                "status": "missing",
                "calculation": {
                    "formula": eval_spec["definition"]["formula"],
                    "elements": [
                        {
                            "id": "reason",
                            "label": "Unavailable reason",
                            "value": "evaluate_answer has not completed in this run yet.",
                        }
                    ],
                },
            }
        ]
    measures.append(eval_measure)

    provenance = dict(updated.get("evaluation") or {})
    run_meta = dict((provenance.get("provenance") or {}).get("run") or {})
    if execution_time_s is not None:
        run_meta["execution_time_s"] = round(float(execution_time_s), 4)
    if evaluation_time_s is not None:
        run_meta["evaluation_time_s"] = round(float(evaluation_time_s), 4)
    if run_meta:
        nested = dict(provenance.get("provenance") or {})
        nested["run"] = run_meta
        provenance["provenance"] = nested
        updated["evaluation"] = provenance

    updated["measures"] = measures
    return updated
