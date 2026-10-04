"""Run the LangGraph pipeline and flatten the last known state."""

from __future__ import annotations

from typing import Any

from src.orchestration.graph import stream_steps


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
    steps: list[str] = []
    for event in events:
        steps.append(str(event["step"]))
        output = event.get("output") or {}
        if isinstance(output, dict):
            merged.update(output)
    result: dict[str, Any] = {
        "question": question,
        "query_id": merged.get("query_id") or query_id or "",
        "status": merged.get("status") or "error",
        "last_step": steps[-1] if steps else "",
        "steps": steps,
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
        result["trace"] = events
    return result
