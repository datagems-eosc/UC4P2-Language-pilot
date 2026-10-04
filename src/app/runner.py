"""Run the LangGraph pipeline and return a step-by-step traceable payload."""

from __future__ import annotations

from typing import Any

from src.orchestration.graph import stream_steps

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
        "name": "export_benchmark",
        "path": "/steps/export",
        "title": "Export the benchmark record",
        "summary": "Package the run as a benchmark record (full ThematicExploration).",
    },
)

_STEP_TITLES = {item["name"]: item["title"] for item in PIPELINE_STEPS}
_OUTCOME_STATUS = {
    "ok": "ok",
    "partial": "partial",
    "halted": "clarification",
    "failed": "error",
}

_HIDDEN_OUTPUT_KEYS = {"pipeline"}


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
    if name == "decompose":
        qdmr = output.get("qdmr") or []
        numbered = ", ".join(f"#{item.get('step')}" for item in qdmr)
        return f"Produced {len(qdmr)} sub-questions ({numbered})."
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
        extra = f" {remote} slice(s) used corpus-analysis-search." if remote else ""
        return f"Computed feature metrics for {len(metrics)} slices.{extra}"
    if name == "synthesize":
        citations = output.get("grounded_citations") or []
        answer = str(output.get("synthesized_answer") or "").strip()
        preview = answer[:160] + ("…" if len(answer) > 160 else "")
        return f"Wrote the answer with {len(citations)} citations. {preview}"
    if name == "export_benchmark":
        record = output.get("benchmark") or {}
        return f"Exported benchmark record {record.get('query_id') or ''}."
    return status or "completed"


def _outcome(name: str, output: dict[str, Any]) -> str:
    status = str(output.get("status") or "")
    if name == "disambiguate" and status == "clarification":
        return "halted"
    if name == "retrieve_slices" and (output.get("retrieval_errors") or {}):
        passages = output.get("passages") or {}
        if any(passages.values()):
            return "partial"
        return "failed"
    if status in {"error", "failed"}:
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
    if last_outcome in {"halted", "failed", "partial"}:
        return derived
    if merged_status in {"ok", "clarification", "partial"}:
        return merged_status
    return derived or merged_status or "error"


def run_compare(
    question: str,
    *,
    query_id: str | None = None,
    until: str | None = None,
    include_trace: bool = False,
    k: int = 5,
) -> dict[str, Any]:
    events = list(
        stream_steps(
            question,
            query_id=query_id,
            until=until,
            k=k,
        )
    )
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
        "clarification": merged.get("clarification"),
        "constraint_errors": merged.get("constraint_errors") or [],
        "concept": merged.get("concept") or "",
        "comparison_type": merged.get("comparison_type") or "",
        "slices": merged.get("slices") or [],
        "qdmr": merged.get("qdmr") or [],
        "search_queries": merged.get("search_queries") or {},
        "passages": merged.get("passages") or {},
        "retrieval_errors": merged.get("retrieval_errors") or {},
        "feature_metrics": merged.get("feature_metrics") or {},
        "synthesized_answer": merged.get("synthesized_answer"),
        "grounded_citations": merged.get("grounded_citations") or [],
        "benchmark": merged.get("benchmark"),
    }
    if include_trace:
        result["raw_trace"] = events
    return result
