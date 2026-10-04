"""Run the LangGraph pipeline and return a step-by-step traceable payload."""

from __future__ import annotations

from typing import Any

from src.orchestration.graph import stream_steps

_STEP_TITLES = {
    "route": "Route the question",
    "disambiguate": "Disambiguate and check archive constraints",
    "extend_knowledge": "Extend knowledge (facets and lemmas)",
    "decompose": "Decompose into sub-questions",
    "retrieve_slices": "Retrieve passages per slice",
    "compute_features": "Measure comparative features",
    "synthesize": "Synthesize a grounded answer",
    "export_benchmark": "Export the benchmark record",
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
        return f"Computed feature metrics for {len(metrics)} slices."
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
        "status": merged.get("status") or "error",
        "last_step": names[-1] if names else "",
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
