"""StudentQuiz-compatible measure definitions for UC4P2 NLG + LLM-as-judge."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "1.0"
EVALUATION_META: dict[str, Any] = {
    "id": "uc4p2-language-pilot",
    "projectId": "uc4p2_language_pilot",
    "label": "UC4P2 Language Pilot",
    "provenance": {
        "sourceFile": "src/evaluation/nlg.py",
        "note": (
            "Measures mirror data/evaluation/StudentQuiz.json (schemaVersion 1.0). "
            "Each observation may include calculation.elements with the inputs used "
            "to produce the value for that run."
        ),
    },
}

_RATIO_UNIT = {"code": "ratio", "symbol": None, "status": "declared"}
_SCALE_UNIT = {"code": None, "symbol": None, "status": "declared"}
_SECOND_UNIT = {"code": "second", "symbol": "s", "status": "declared"}


def _dim() -> list[dict[str, Any]]:
    return [
        {
            "id": "run_id",
            "label": "Execution / run ID",
            "type": "nominal",
            "role": "category",
            "required": True,
        },
        {
            "id": "query_id",
            "label": "Question / Subquestion ID",
            "type": "nominal",
            "role": "group",
            "required": True,
        },
        {
            "id": "operator",
            "label": "Pipeline operator",
            "type": "nominal",
            "role": "group",
            "required": True,
        },
        {
            "id": "gold_source",
            "label": "Gold source",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
        {
            "id": "llm_model",
            "label": "Pipeline LLM",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
        {
            "id": "judge_llm_model",
            "label": "Judge LLM",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
    ]


def _step_dim() -> list[dict[str, Any]]:
    return [
        {
            "id": "run_id",
            "label": "Execution / run ID",
            "type": "nominal",
            "role": "group",
            "required": True,
        },
        {
            "id": "operator",
            "label": "Pipeline operator / step",
            "type": "nominal",
            "role": "category",
            "required": True,
        },
        {
            "id": "query_id",
            "label": "Question / Subquestion ID",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
        {
            "id": "llm_model",
            "label": "Pipeline LLM",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
        {
            "id": "judge_llm_model",
            "label": "Judge LLM",
            "type": "nominal",
            "role": "group",
            "required": False,
        },
    ]


MEASURE_SPECS: list[dict[str, Any]] = [
    {
        "id": "uc4p2.exact_match",
        "family": "data",
        "label": "Exact match",
        "description": (
            "Binary equality of the synthesized answer and ground truth after "
            "stripping [ref_N] citation marks, lowercasing, and dropping punctuation."
        ),
        "metric_key": "exact_match",
        "definition": {
            "key": "uc4p2.exact_match",
            "version": "1.0",
            "status": "defined",
            "formula": "1 if normalize(strip_citations(hyp)) == normalize(ref) else 0",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.token_precision",
        "family": "data",
        "label": "Token precision",
        "description": "Bag-of-tokens precision of hypothesis unigrams against the reference.",
        "metric_key": "token_precision",
        "definition": {
            "key": "uc4p2.token_precision",
            "version": "1.0",
            "status": "defined",
            "formula": "overlap / |hyp_tokens|  (clipped multiset overlap)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.token_recall",
        "family": "data",
        "label": "Token recall",
        "description": "Bag-of-tokens recall of hypothesis unigrams against the reference.",
        "metric_key": "token_recall",
        "definition": {
            "key": "uc4p2.token_recall",
            "version": "1.0",
            "status": "defined",
            "formula": "overlap / |ref_tokens|  (clipped multiset overlap)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.token_f1",
        "family": "data",
        "label": "Token F1",
        "description": "Harmonic mean of token precision and token recall.",
        "metric_key": "token_f1",
        "definition": {
            "key": "uc4p2.token_f1",
            "version": "1.0",
            "status": "defined",
            "formula": "2 * P * R / (P + R)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.bleu",
        "family": "data",
        "label": "BLEU",
        "description": (
            "Sentence BLEU with uniform weights over 1–4 gram clipped precision "
            "and a brevity penalty."
        ),
        "metric_key": "bleu",
        "definition": {
            "key": "uc4p2.bleu",
            "version": "1.0",
            "status": "defined",
            "formula": "BP * exp(mean(log p_n)) for n=1..4; BP = exp(1 - |ref|/|hyp|) if |hyp| < |ref| else 1",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.bleu_1",
        "family": "data",
        "label": "BLEU-1 precision",
        "description": "Clipped unigram precision component of BLEU.",
        "metric_key": "bleu_1",
        "definition": {
            "key": "uc4p2.bleu_1",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_overlap(1-grams) / |hyp 1-grams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.bleu_2",
        "family": "data",
        "label": "BLEU-2 precision",
        "description": "Clipped bigram precision component of BLEU.",
        "metric_key": "bleu_2",
        "definition": {
            "key": "uc4p2.bleu_2",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_overlap(2-grams) / |hyp 2-grams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.bleu_3",
        "family": "data",
        "label": "BLEU-3 precision",
        "description": "Clipped trigram precision component of BLEU.",
        "metric_key": "bleu_3",
        "definition": {
            "key": "uc4p2.bleu_3",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_overlap(3-grams) / |hyp 3-grams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.bleu_4",
        "family": "data",
        "label": "BLEU-4 precision",
        "description": "Clipped 4-gram precision component of BLEU.",
        "metric_key": "bleu_4",
        "definition": {
            "key": "uc4p2.bleu_4",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_overlap(4-grams) / |hyp 4-grams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.brevity_penalty",
        "family": "data",
        "label": "BLEU brevity penalty",
        "description": "BLEU brevity penalty applied to the geometric mean of n-gram precisions.",
        "metric_key": "brevity_penalty",
        "definition": {
            "key": "uc4p2.brevity_penalty",
            "version": "1.0",
            "status": "defined",
            "formula": "1 if |hyp| >= |ref| else exp(1 - |ref|/|hyp|)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge1_f1",
        "family": "data",
        "label": "ROUGE-1 F1",
        "description": "Unigram ROUGE F1 between hypothesis and reference.",
        "metric_key": "rouge1_f1",
        "definition": {
            "key": "uc4p2.rouge1_f1",
            "version": "1.0",
            "status": "defined",
            "formula": "F1 of clipped unigram overlap (P = overlap/|hyp|, R = overlap/|ref|)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge1_precision",
        "family": "data",
        "label": "ROUGE-1 precision",
        "description": "Unigram ROUGE precision.",
        "metric_key": "rouge1_precision",
        "definition": {
            "key": "uc4p2.rouge1_precision",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_unigram_overlap / |hyp_unigrams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge1_recall",
        "family": "data",
        "label": "ROUGE-1 recall",
        "description": "Unigram ROUGE recall.",
        "metric_key": "rouge1_recall",
        "definition": {
            "key": "uc4p2.rouge1_recall",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_unigram_overlap / |ref_unigrams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge2_f1",
        "family": "data",
        "label": "ROUGE-2 F1",
        "description": "Bigram ROUGE F1 between hypothesis and reference.",
        "metric_key": "rouge2_f1",
        "definition": {
            "key": "uc4p2.rouge2_f1",
            "version": "1.0",
            "status": "defined",
            "formula": "F1 of clipped bigram overlap",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge2_precision",
        "family": "data",
        "label": "ROUGE-2 precision",
        "description": "Bigram ROUGE precision.",
        "metric_key": "rouge2_precision",
        "definition": {
            "key": "uc4p2.rouge2_precision",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_bigram_overlap / |hyp_bigrams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rouge2_recall",
        "family": "data",
        "label": "ROUGE-2 recall",
        "description": "Bigram ROUGE recall.",
        "metric_key": "rouge2_recall",
        "definition": {
            "key": "uc4p2.rouge2_recall",
            "version": "1.0",
            "status": "defined",
            "formula": "clipped_bigram_overlap / |ref_bigrams|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rougeL_f1",
        "family": "data",
        "label": "ROUGE-L F1",
        "description": "Longest common subsequence F1 between hypothesis and reference tokens.",
        "metric_key": "rougeL_f1",
        "definition": {
            "key": "uc4p2.rougeL_f1",
            "version": "1.0",
            "status": "defined",
            "formula": "F1 with P = LCS/|hyp|, R = LCS/|ref|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rougeL_precision",
        "family": "data",
        "label": "ROUGE-L precision",
        "description": "LCS precision component of ROUGE-L.",
        "metric_key": "rougeL_precision",
        "definition": {
            "key": "uc4p2.rougeL_precision",
            "version": "1.0",
            "status": "defined",
            "formula": "LCS_length / |hyp_tokens|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.rougeL_recall",
        "family": "data",
        "label": "ROUGE-L recall",
        "description": "LCS recall component of ROUGE-L.",
        "metric_key": "rougeL_recall",
        "definition": {
            "key": "uc4p2.rougeL_recall",
            "version": "1.0",
            "status": "defined",
            "formula": "LCS_length / |ref_tokens|",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.meteor",
        "family": "data",
        "label": "METEOR (unigram)",
        "description": (
            "Simplified METEOR: unigram harmonic mean with a fragmentation penalty. "
            "No synonym/stemming module."
        ),
        "metric_key": "meteor",
        "definition": {
            "key": "uc4p2.meteor",
            "version": "1.0",
            "status": "defined",
            "formula": "Fmean * (1 - 0.5 * (chunks/matches)^3); Fmean = 2PR/(P+R)",
        },
        "valueType": "number",
        "unit": _RATIO_UNIT,
        "scale": {"min": 0, "max": 1},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.judge_score",
        "family": "human",
        "label": "LLM-as-judge overall score",
        "description": (
            "Overall quality of the system answer vs gold, scored 1–5 by a second "
            "Scayle model (not the synthesizer)."
        ),
        "metric_key": "judge.score",
        "definition": {
            "key": "uc4p2.judge_score",
            "version": "1.0",
            "status": "defined",
            "formula": "Integer 1–5 from judge LLM JSON field `score`",
        },
        "valueType": "number",
        "unit": _SCALE_UNIT,
        "scale": {"min": 1, "max": 5},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.judge_faithfulness",
        "family": "human",
        "label": "LLM-as-judge faithfulness",
        "description": "1–5: system answer does not contradict the gold answer.",
        "metric_key": "judge.faithfulness",
        "definition": {
            "key": "uc4p2.judge_faithfulness",
            "version": "1.0",
            "status": "defined",
            "formula": "Integer 1–5 from judge LLM JSON field `faithfulness`",
        },
        "valueType": "number",
        "unit": _SCALE_UNIT,
        "scale": {"min": 1, "max": 5},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
    {
        "id": "uc4p2.judge_coverage",
        "family": "human",
        "label": "LLM-as-judge coverage",
        "description": "1–5: gold facts present in the system answer.",
        "metric_key": "judge.coverage",
        "definition": {
            "key": "uc4p2.judge_coverage",
            "version": "1.0",
            "status": "defined",
            "formula": "Integer 1–5 from judge LLM JSON field `coverage`",
        },
        "valueType": "number",
        "unit": _SCALE_UNIT,
        "scale": {"min": 1, "max": 5},
        "objective": "maximize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
    },
]

SYSTEM_MEASURE_SPECS: list[dict[str, Any]] = [
    {
        "id": "uc4p2.execution_time",
        "family": "system",
        "label": "Step execution time",
        "description": (
            "Wall-clock seconds spent inside each LangGraph pipeline operator "
            "(route, disambiguate, …, evaluate_answer, export_benchmark)."
        ),
        "metric_key": "execution_time",
        "definition": {
            "key": "uc4p2.execution_time",
            "version": "1.0",
            "status": "defined",
            "formula": "time.perf_counter() delta from previous step yield to this step yield",
        },
        "valueType": "number",
        "unit": _SECOND_UNIT,
        "scale": {"min": 0, "max": None},
        "objective": "minimize",
        "aggregation": {"default": "sum", "allowed": ["none", "sum", "mean"]},
        "dimensions": _step_dim(),
        "visualization": {"preferred": "bar", "x": "operator", "y": "value"},
        "provenance": {
            "sourceFile": "src/orchestration/graph.py",
            "sourceMeasure": "duration_s",
        },
    },
    {
        "id": "uc4p2.execution_time_total",
        "family": "system",
        "label": "Total pipeline execution time",
        "description": "Sum of per-step wall-clock durations for the completed run.",
        "metric_key": "execution_time_total",
        "definition": {
            "key": "uc4p2.execution_time_total",
            "version": "1.0",
            "status": "defined",
            "formula": "sum(duration_s for each completed pipeline step)",
        },
        "valueType": "number",
        "unit": _SECOND_UNIT,
        "scale": {"min": 0, "max": None},
        "objective": "minimize",
        "aggregation": {"default": "none", "allowed": ["none"]},
        "dimensions": _dim(),
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
        "provenance": {
            "sourceFile": "src/app/runner.py",
            "sourceMeasure": "execution_time_s",
        },
    },
    {
        "id": "uc4p2.evaluation_time",
        "family": "system",
        "label": "Evaluation execution time",
        "description": (
            "Wall-clock seconds for the evaluate_answer operator "
            "(NLG metrics + optional LLM-as-judge)."
        ),
        "metric_key": "evaluation_time",
        "definition": {
            "key": "uc4p2.evaluation_time",
            "version": "1.0",
            "status": "defined",
            "formula": "duration_s of pipeline step evaluate_answer",
        },
        "valueType": "number",
        "unit": _SECOND_UNIT,
        "scale": {"min": 0, "max": None},
        "objective": "minimize",
        "aggregation": {"default": "mean", "allowed": ["none", "mean"]},
        "dimensions": _dim(),
        "visualization": {"preferred": "bar", "x": "query_id", "y": "value"},
        "provenance": {
            "sourceFile": "src/app/runner.py",
            "sourceMeasure": "evaluation_time_s",
        },
    },
]


def _measure_from_spec(spec: dict[str, Any], *, dimensions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
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
        "dimensions": list(dimensions if dimensions is not None else spec.get("dimensions") or _dim()),
        "observations": [],
        "visualization": dict(spec["visualization"]),
        "provenance": dict(spec.get("provenance") or {}),
    }


def empty_measure_catalog() -> dict[str, Any]:
    """Catalog-only document (no observations), StudentQuiz-compatible."""
    measures = []
    for spec in MEASURE_SPECS:
        item = _measure_from_spec(spec, dimensions=_dim())
        item["provenance"] = {
            "sourceFile": "src/evaluation/nlg.py"
            if not str(spec["metric_key"]).startswith("judge.")
            else "src/evaluation/judge.py",
            "sourceMeasure": spec["metric_key"],
        }
        measures.append(item)
    for spec in SYSTEM_MEASURE_SPECS:
        measures.append(_measure_from_spec(spec))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "evaluation": dict(EVALUATION_META),
        "measures": measures,
    }
