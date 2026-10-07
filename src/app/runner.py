"""Run the LangGraph pipeline and return a step-by-step traceable payload."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.app.auth import caller_access_token
from src.constraints.comparative import QueryDisambiguationClient
from src.decomposition.modes import FEW_SHOT
from src.orchestration.graph import stream_steps
from src.orchestration.slice_executor import CrossDatasetDiscoveryClient

logger = logging.getLogger(__name__)

_TASK_NAME = re.compile(r"During task with name '([^']+)'")

PIPELINE_STEPS = (
    {
        "name": "route",
        "path": "/steps/route",
        "title": "Route the question",
        "summary": "Classify the question and extract the comparison concept.",
    },
    {
        "name": "disambiguate",
        "path": "/steps/disambiguate",
        "title": "Disambiguate and check archive constraints",
        "summary": "Resolve slices and reject queries the archive cannot answer.",
    },
    {
        "name": "extend_knowledge",
        "path": "/steps/extend-knowledge",
        "title": "Extend knowledge (facets and lemmas)",
        "summary": "Expand thematic facets and lexical variants per slice.",
    },
    {
        "name": "generate_subquestions",
        "path": "/steps/generate-subquestions",
        "title": "Create sub-questions from facets and lemmas",
        "summary": "Turn thematic facets and per-slice lemmas into retrieval sub-questions.",
    },
    {
        "name": "decompose",
        "path": "/steps/decompose",
        "title": "Decompose into sub-questions",
        "summary": "Turn the comparison into QDMR sub-questions.",
    },
    {
        "name": "retrieve_slices",
        "path": "/steps/retrieve",
        "title": "Retrieve passages per slice",
        "summary": "Search Cross-Dataset Discovery once per comparison slice.",
    },
    {
        "name": "compute_features",
        "path": "/steps/features",
        "title": "Measure comparative features",
        "summary": "Measure comparative features via Cross-Dataset Discovery corpus-analysis-search.",
    },
    {
        "name": "synthesize",
        "path": "/steps/synthesize",
        "title": "Synthesize a grounded answer",
        "summary": "Write the comparative answer with citations.",
    },
    {
        "name": "evaluate_answer",
        "path": "/steps/evaluate",
        "title": "Evaluate against ground truth",
        "summary": "Score the synthesized answer against Pilot 2 ground truth with NLG metrics.",
    },
    {
        "name": "export_benchmark",
        "path": "/steps/export",
        "title": "Export the benchmark record",
        "summary": "Package the run as a benchmark record (full ThematicExploration).",
    },
)

_STEP_TITLES = {item["name"]: item["title"] for item in PIPELINE_STEPS}
_STEP_ORDER = [item["name"] for item in PIPELINE_STEPS]
_OUTCOME_STATUS = {
    "ok": "ok",
    "partial": "partial",
    "halted": "clarification",
    "failed": "error",
    "timeout": "timeout",
}

_HIDDEN_OUTPUT_KEYS = {"pipeline"}


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc).lower()
    if "timed out" in message or "timeout" in message:
        return True
    cause = exc.__cause__ or exc.__context__
    return bool(cause and _is_timeout(cause))


def _failed_step_name(exc: BaseException, completed: list[str]) -> str:
    for candidate in (exc, exc.__cause__, exc.__context__):
        if candidate is None:
            continue
        match = _TASK_NAME.search(str(candidate))
        if match and match.group(1) in _STEP_TITLES:
            return match.group(1)
    if not completed:
        return _STEP_ORDER[0]
    try:
        index = _STEP_ORDER.index(completed[-1])
    except ValueError:
        return completed[-1]
    if index + 1 < len(_STEP_ORDER):
        return _STEP_ORDER[index + 1]
    return completed[-1]


def _strip_internal(output: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in output.items() if key not in _HIDDEN_OUTPUT_KEYS}


def _summarize(name: str, output: dict[str, Any]) -> str:
    status = str(output.get("status") or "")
    if name == "route":
        concept = (output.get("route") or {}).get("concept") or output.get("concept") or ""
        return f"Routed as a comparative question about {concept or 'an unspecified concept'}."
    if name == "disambiguate":
        if status == "clarification":
            return str(output.get("clarification") or "The query cannot proceed.")
        slices = output.get("slices") or []
        labels = ", ".join(str(item.get("label") or item.get("slice_id")) for item in slices)
        return (
            f"Comparison type {output.get('comparison_type') or 'unknown'} "
            f"over {len(slices)} slices ({labels}). "
            f"Source: {output.get('disambiguation_source') or 'unknown'}."
        )
    if name == "extend_knowledge":
        expansion = output.get("expansion") or {}
        facets = expansion.get("thematic_facets") or []
        return f"Expanded {len(facets)} thematic facets across {max(0, len(expansion) - 2)} slice lexicons."
    if name == "generate_subquestions":
        items = output.get("generated_subquestions") or []
        return f"Created {len(items)} sub-questions from thematic facets and lemmas."
    if name == "decompose":
        qdmr = output.get("qdmr") or []
        numbered = ", ".join(f"#{item.get('step')}" for item in qdmr)
        mode = output.get("decompose_mode") or FEW_SHOT
        return f"Produced {len(qdmr)} sub-questions ({numbered}) with {mode} decomposition."
    if name == "retrieve_slices":
        passages = output.get("passages") or {}
        errors = output.get("retrieval_errors") or {}
        counts = ", ".join(f"{slice_id}: {len(items)} hits" for slice_id, items in passages.items())
        if errors:
            failed = ", ".join(errors)
            return f"Retrieved {counts or 'no passages'}. Failed slices: {failed}."
        return f"Retrieved {counts or 'no passages'}."
    if name == "compute_features":
        metrics = output.get("feature_metrics") or {}
        remote = sum(
            1
            for item in metrics.values()
            if isinstance(item, dict)
            and (item.get("corpus_analysis") or {}).get("source")
            == "cross-dataset-discovery/corpus-analysis-search"
        )
        soft_fails = [
            f"{slice_id}: {((item or {}).get('corpus_analysis') or {}).get('error')}"
            for slice_id, item in metrics.items()
            if isinstance(item, dict) and ((item.get("corpus_analysis") or {}).get("error"))
        ]
        extra = f" {remote} slice(s) used corpus-analysis-search." if remote else ""
        if soft_fails:
            extra += " Soft-failed corpus-analysis: " + "; ".join(soft_fails[:3])
            if len(soft_fails) > 3:
                extra += f" (+{len(soft_fails) - 3} more)"
        return f"Computed feature metrics for {len(metrics)} slices.{extra}"
    if name == "synthesize":
        citations = output.get("grounded_citations") or []
        used = [item for item in citations if item.get("used_in_answer", True)]
        answer = str(output.get("synthesized_answer") or "").strip()
        preview = answer[:160] + ("…" if len(answer) > 160 else "")
        return f"Wrote the answer with {len(used)} of {len(citations)} retrieval citations. {preview}"
    if name == "evaluate_answer":
        evaluation = output.get("nlg_evaluation") or {}
        judge = evaluation.get("llm_judge") or {}
        base = str(evaluation.get("summary") or "NLG evaluation did not match a ground-truth row.")
        if judge.get("available"):
            return base
        if judge.get("reason"):
            return f"{base} Judge skipped: {judge['reason']}"
        return base
    if name == "export_benchmark":
        record = output.get("benchmark") or {}
        return f"Exported benchmark record {record.get('query_id') or ''}."
    if output.get("error"):
        return str(output.get("summary") or output["error"])
    return status or "completed"


def _outcome(name: str, output: dict[str, Any]) -> str:
    status = str(output.get("status") or "")
    if output.get("error_kind") == "timeout" or status == "timeout":
        return "timeout"
    if name == "disambiguate" and status == "clarification":
        return "halted"
    if name == "retrieve_slices" and (output.get("retrieval_errors") or {}):
        passages = output.get("passages") or {}
        if any(passages.values()):
            return "partial"
        return "failed"
    if status in {"error", "failed"}:
        return "failed"
    if output.get("error"):
        return "failed"
    return "ok"


def build_pipeline_trace(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn LangGraph node updates into an explicit, auditable step list."""
    trace: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        name = str(event.get("step") or f"step_{index}")
        raw = event.get("output") if isinstance(event.get("output"), dict) else {}
        public = _strip_internal(raw)
        trace.append(
            {
                "step": index,
                "name": name,
                "title": _STEP_TITLES.get(name, name.replace("_", " ").title()),
                "outcome": _outcome(name, public),
                "summary": _summarize(name, public),
                "output": public,
            }
        )
    return trace


def _overall_status(pipeline: list[dict[str, Any]], merged: dict[str, Any]) -> str:
    last_outcome = pipeline[-1]["outcome"] if pipeline else ""
    derived = _OUTCOME_STATUS.get(last_outcome, "")
    merged_status = str(merged.get("status") or "")
    if last_outcome in {"halted", "failed", "partial", "timeout"}:
        return derived
    if merged_status in {"ok", "clarification", "partial", "timeout", "error"}:
        return merged_status
    return derived or merged_status or "error"


def _payload_from_events(
    question: str,
    events: list[dict[str, Any]],
    *,
    query_id: str | None,
    decompose_mode: str,
    include_trace: bool,
) -> dict[str, Any]:
    merged: dict[str, Any] = {"question": question}
    names: list[str] = []
    for event in events:
        names.append(str(event["step"]))
        output = event.get("output") or {}
        if isinstance(output, dict):
            merged.update(_strip_internal(output))
    pipeline = build_pipeline_trace(events)
    result: dict[str, Any] = {
        "question": question,
        "query_id": merged.get("query_id") or query_id or "",
        "status": _overall_status(pipeline, merged),
        "last_step": names[-1] if names else "",
        "result": pipeline[-1] if pipeline else None,
        "pipeline": pipeline,
        "steps": names,
        "failed_step": None,
        "error": None,
        "clarification": merged.get("clarification"),
        "constraint_errors": merged.get("constraint_errors") or [],
        "concept": merged.get("concept") or "",
        "comparison_type": merged.get("comparison_type") or "",
        "slices": merged.get("slices") or [],
        "qdmr": merged.get("qdmr") or [],
        "generated_subquestions": merged.get("generated_subquestions") or [],
        "decompose_mode": merged.get("decompose_mode") or decompose_mode,
        "search_queries": merged.get("search_queries") or {},
        "passages": merged.get("passages") or {},
        "retrieval_errors": merged.get("retrieval_errors") or {},
        "feature_metrics": merged.get("feature_metrics") or {},
        "synthesized_answer": merged.get("synthesized_answer"),
        "grounded_citations": merged.get("grounded_citations") or [],
        "nlg_evaluation": merged.get("nlg_evaluation") or {},
        "benchmark": merged.get("benchmark"),
    }
    if include_trace:
        result["raw_trace"] = events
    return result


def _attach_failure(
    result: dict[str, Any],
    exc: BaseException,
) -> dict[str, Any]:
    """Keep completed steps and record which node timed out or failed."""
    completed = list(result.get("steps") or [])
    failed_step = _failed_step_name(exc, completed)
    timed_out = _is_timeout(exc)
    outcome = "timeout" if timed_out else "failed"
    status = "timeout" if timed_out else "error"
    message = str(exc).strip() or type(exc).__name__
    kind = "timeout" if timed_out else "error"
    summary = (
        f"Timed out during `{failed_step}`: {message}"
        if timed_out
        else f"Failed during `{failed_step}`: {message}"
    )
    failure_step = {
        "step": len(result.get("pipeline") or []) + 1,
        "name": failed_step,
        "title": _STEP_TITLES.get(failed_step, failed_step.replace("_", " ").title()),
        "outcome": outcome,
        "summary": summary,
        "output": {
            "status": status,
            "error": message,
            "error_type": type(exc).__name__,
            "error_kind": kind,
            "failed_step": failed_step,
            "completed_steps": completed,
        },
    }
    pipeline = list(result.get("pipeline") or [])
    # Avoid duplicating the same node if LangGraph already emitted a partial update.
    if pipeline and pipeline[-1].get("name") == failed_step and pipeline[-1].get("outcome") == "ok":
        pipeline[-1] = {**failure_step, "step": pipeline[-1]["step"]}
    else:
        pipeline.append(failure_step)
    steps = list(completed)
    if failed_step not in steps:
        steps.append(failed_step)
    result.update(
        {
            "status": status,
            "last_step": failed_step,
            "failed_step": failed_step,
            "error": summary,
            "pipeline": pipeline,
            "result": pipeline[-1],
            "steps": steps,
        }
    )
    return result


def run_compare(
    question: str,
    *,
    query_id: str | None = None,
    until: str | None = None,
    include_trace: bool = False,
    k: int = 5,
    decompose_mode: str = FEW_SHOT,
) -> dict[str, Any]:
    token = caller_access_token()
    events: list[dict[str, Any]] = []
    failure: BaseException | None = None
    try:
        for event in stream_steps(
            question,
            query_id=query_id,
            until=until,
            k=k,
            decompose_mode=decompose_mode,
            disambiguation_client=QueryDisambiguationClient(token=token) if token else None,
            retrieval_client=CrossDatasetDiscoveryClient(token=token) if token else None,
        ):
            events.append(event)
    except Exception as exc:  # noqa: BLE001 - surface as structured pipeline failure
        failure = exc
        logger.exception(
            "pipeline interrupted after %s steps until=%s",
            len(events),
            until,
        )
    result = _payload_from_events(
        question,
        events,
        query_id=query_id,
        decompose_mode=decompose_mode,
        include_trace=include_trace,
    )
    if failure is not None:
        return _attach_failure(result, failure)
    return result
