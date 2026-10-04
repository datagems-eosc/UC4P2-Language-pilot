"""Request and response models for the Pilot 2 API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    query_id: Optional[str] = None
    include_trace: bool = Field(
        default=False,
        description="If true, also return the raw LangGraph node updates as raw_trace.",
    )
    k: Optional[int] = Field(default=None, ge=1, le=20)


class ThematicExplorationRequest(QueryRequest):
    until: Optional[str] = Field(
        default=None,
        description=(
            "Stop after this LangGraph node: route, disambiguate, extend_knowledge, "
            "decompose, retrieve_slices, compute_features, synthesize, export_benchmark."
        ),
    )


CompareRequest = ThematicExplorationRequest


class PipelineStep(BaseModel):
    """One executed pipeline node and what it produced."""

    step: int
    name: str
    title: str
    outcome: str
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)


class ThematicExplorationResponse(BaseModel):
    service: str = "UC4P2 Language Pilot"
    query_id: str = ""
    question: str
    status: str
    last_step: str = ""
    result: Optional[PipelineStep] = Field(
        default=None,
        description="The last executed step (the target of a /steps/* call).",
    )
    pipeline: list[PipelineStep] = Field(
        default_factory=list,
        description="Ordered steps with outcome and output so the answer is traceable.",
    )
    clarification: Optional[str] = None
    constraint_errors: list[str] = Field(default_factory=list)
    concept: str = ""
    comparison_type: str = ""
    slices: list[dict[str, Any]] = Field(default_factory=list)
    qdmr: list[dict[str, Any]] = Field(default_factory=list)
    search_queries: dict[str, str] = Field(default_factory=dict)
    passages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    retrieval_errors: dict[str, str] = Field(default_factory=dict)
    feature_metrics: dict[str, Any] = Field(default_factory=dict)
    synthesized_answer: Optional[str] = None
    grounded_citations: list[dict[str, Any]] = Field(default_factory=list)
    benchmark: Optional[dict[str, Any]] = None
    steps: list[str] = Field(default_factory=list)
    raw_trace: Optional[list[dict[str, Any]]] = None


CompareResponse = ThematicExplorationResponse
