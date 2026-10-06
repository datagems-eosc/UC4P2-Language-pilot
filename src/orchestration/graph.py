"""LangGraph runner for Pilot 2.

Each pipeline stage is a node. ``stream_steps`` yields that node's update
as soon as it finishes, so a run can be inspected one step at a time.
Retrieval still calls Cross-Dataset Discovery, once per slice, in parallel.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.constraints.comparative import QueryDisambiguationClient
from src.decomposition.modes import FEW_SHOT
from src.orchestration.pipeline import HistoricalQAOrchestrator
from src.orchestration.slice_executor import CrossDatasetDiscoveryClient
from src.retrieval.multi_slice_retriever import CrossDatasetMultiSliceRetriever
from src.routing.router import route_query
from src.schemas.state import PipelineState


class PilotState(TypedDict, total=False):
    question: str
    query_id: str
    status: str
    domain: str
    route: dict[str, Any]
    concept: str
    comparison_type: str
    slices: list[dict[str, Any]]
    pipeline: dict[str, Any]
    disambiguation: dict[str, Any]
    disambiguation_source: str
    clarification: str | None
    constraint_errors: list[str]
    expansion: dict[str, Any]
    generated_subquestions: list[dict[str, str]]
    qdmr: list[dict[str, Any]]
    decompose_mode: str
    search_queries: dict[str, str]
    passages: dict[str, list[dict[str, Any]]]
    retrieval_errors: dict[str, str]
    feature_metrics: dict[str, Any]
    synthesized_answer: str
    grounded_citations: list[dict[str, Any]]
    nlg_evaluation: dict[str, Any]
    benchmark: dict[str, Any]


def _load(state: PilotState) -> PipelineState:
    return PipelineState.model_validate(state["pipeline"])


def _dump(pipeline: PipelineState) -> dict[str, Any]:
    return pipeline.model_dump(mode="json")


def build_pilot_graph(
    disambiguation_client: QueryDisambiguationClient | None = None,
    retrieval_client: CrossDatasetDiscoveryClient | None = None,
    k: int = 5,
    decompose_mode: str = FEW_SHOT,
):
    retriever = CrossDatasetMultiSliceRetriever(client=retrieval_client, k=k)
    orchestrator = HistoricalQAOrchestrator(
        disambiguation_client, retriever, decompose_mode=decompose_mode
    )

    def route(state: PilotState) -> dict[str, Any]:
        decision = route_query(state["question"])
        return {"domain": "comparative", "route": {"domain": "comparative", "concept": decision.concept}}

    def disambiguate(state: PilotState) -> dict[str, Any]:
        resolved = orchestrator.resolve(state["question"], state.get("query_id"))
        intent = resolved.intent
        remote = resolved.disambiguation or {}
        return {
            "pipeline": _dump(resolved),
            "query_id": resolved.query_id,
            "status": resolved.status,
            "disambiguation": remote,
            "disambiguation_source": resolved.disambiguation_source,
            "clarification": resolved.clarification,
            "constraint_errors": resolved.constraint_errors,
            "concept": intent.target_concept if intent else "",
            "comparison_type": str(remote.get("comparison_type") or (intent.dimension if intent else "")),
            "slices": [item.model_dump() for item in intent.slices] if intent else [],
        }

    def extend_knowledge(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.extend(_load(state))
        return {"pipeline": _dump(updated), "expansion": updated.knowledge_extension, "status": updated.status}

    def generate_subquestions(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.generate_subquestions(_load(state))
        return {
            "pipeline": _dump(updated),
            "generated_subquestions": updated.generated_subquestions,
            "status": updated.status,
        }

    def decompose(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.decompose(_load(state))
        qdmr = [
            {"step": index, "instruction": task}
            for index, task in enumerate(updated.sub_tasks, start=1)
        ]
        return {
            "pipeline": _dump(updated),
            "qdmr": qdmr,
            "decompose_mode": updated.decompose_mode or decompose_mode,
            "status": updated.status,
        }

    def retrieve_slices(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.retrieve(_load(state))
        visible = {
            slice_id: [
                {
                    "slice_id": item.get("slice_id"),
                    "doc_id": item.get("doc_id"),
                    "dataset_id": item.get("dataset_id"),
                    "similarity": item.get("similarity"),
                    "text": item.get("text"),
                    "text_snippet": item.get("text"),
                }
                for item in items
            ]
            for slice_id, items in updated.passages.items()
        }
        return {
            "pipeline": _dump(updated),
            "passages": visible,
            "search_queries": updated.search_queries,
            "retrieval_errors": updated.retrieval_errors,
            "status": updated.status,
        }

    def compute_features(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.measure(_load(state))
        return {
            "pipeline": _dump(updated),
            "feature_metrics": updated.feature_metrics,
            "status": updated.status,
        }

    def synthesize(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.synthesize(_load(state))
        output = updated.output
        assert output is not None
        return {
            "pipeline": _dump(updated),
            "synthesized_answer": output.synthesized_answer,
            "grounded_citations": [item.model_dump() for item in output.grounded_citations],
            "status": updated.status,
        }

    def evaluate_answer(state: PilotState) -> dict[str, Any]:
        updated = orchestrator.evaluate(_load(state))
        return {
            "pipeline": _dump(updated),
            "nlg_evaluation": updated.nlg_evaluation,
            "status": updated.status,
        }

    def export_benchmark(state: PilotState) -> dict[str, Any]:
        current = _load(state)
        assert current.output is not None
        return {"status": "ok", "benchmark": current.output.model_dump(mode="json")}

    def after_disambiguate(state: PilotState) -> str:
        if state.get("status") == "clarification":
            return END
        return "extend_knowledge"

    graph = StateGraph(PilotState)
    graph.add_node("route", route)
    graph.add_node("disambiguate", disambiguate)
    graph.add_node("extend_knowledge", extend_knowledge)
    graph.add_node("generate_subquestions", generate_subquestions)
    graph.add_node("decompose", decompose)
    graph.add_node("retrieve_slices", retrieve_slices)
    graph.add_node("compute_features", compute_features)
    graph.add_node("synthesize", synthesize)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("export_benchmark", export_benchmark)

    graph.add_edge(START, "route")
    graph.add_edge("route", "disambiguate")
    graph.add_conditional_edges(
        "disambiguate",
        after_disambiguate,
        {"extend_knowledge": "extend_knowledge", END: END},
    )
    graph.add_edge("extend_knowledge", "generate_subquestions")
    graph.add_edge("generate_subquestions", "decompose")
    graph.add_edge("decompose", "retrieve_slices")
    graph.add_edge("retrieve_slices", "compute_features")
    graph.add_edge("compute_features", "synthesize")
    graph.add_edge("synthesize", "evaluate_answer")
    graph.add_edge("evaluate_answer", "export_benchmark")
    graph.add_edge("export_benchmark", END)
    return graph.compile()


def stream_steps(
    question: str,
    *,
    query_id: str | None = None,
    until: str | None = None,
    disambiguation_client: QueryDisambiguationClient | None = None,
    retrieval_client: CrossDatasetDiscoveryClient | None = None,
    k: int = 5,
    decompose_mode: str = FEW_SHOT,
) -> Iterator[dict[str, Any]]:
    """Yield ``{"step": name, "output": update}`` after each node."""
    compiled = build_pilot_graph(
        disambiguation_client,
        retrieval_client,
        k=k,
        decompose_mode=decompose_mode,
    )
    initial: PilotState = {"question": question}
    if query_id:
        initial["query_id"] = query_id
    for update in compiled.stream(initial, stream_mode="updates"):
        for name, output in update.items():
            event = {"step": name, "output": output}
            yield event
            if until and name == until:
                return


def main() -> None:
    import argparse
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    from src.llm import configure_lm_from_env

    load_dotenv()
    configured = configure_lm_from_env()
    parser = argparse.ArgumentParser(
        description="Run Pilot 2 in LangGraph and print each step as it finishes."
    )
    parser.add_argument("question")
    parser.add_argument("--query-id", default=None)
    parser.add_argument(
        "--until",
        default=None,
        help="Stop after this node (route, disambiguate, extend_knowledge, generate_subquestions, "
        "decompose, retrieve_slices, compute_features, synthesize, evaluate_answer, export_benchmark).",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional JSON file for the ordered step trace.",
    )
    args = parser.parse_args()
    if configured:
        provider = os.getenv("LLM_PROVIDER", "").strip().lower() or "gemini"
        print(f"LLM provider: {provider}")
    else:
        print("LLM: not configured; expansion and decomposition use the built-in lexicon.")
    trace: list[dict[str, Any]] = []
    for event in stream_steps(args.question, query_id=args.query_id, until=args.until):
        trace.append(event)
        print(f"\n===== {event['step']} =====")
        print(json.dumps(event["output"], indent=2, ensure_ascii=False, default=str))
    if args.out:
        destination = Path(args.out)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(trace, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {len(trace)} steps to {destination}")


if __name__ == "__main__":
    main()
