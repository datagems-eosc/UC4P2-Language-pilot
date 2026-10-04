"""Execution state shared by the orchestrator and the LangGraph runner."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from src.schemas.benchmark import BenchmarkOutput
from src.schemas.slice import ParsedQueryIntent


class PipelineState(BaseModel):
    """Complete state after a comparative run, including a halted clarification."""

    question: str
    query_id: str
    status: str
    intent: Optional[ParsedQueryIntent] = None
    disambiguation: dict[str, Any] = Field(default_factory=dict)
    disambiguation_source: str = ""
    clarification: Optional[str] = None
    constraint_errors: list[str] = Field(default_factory=list)
    knowledge_extension: dict[str, list[str]] = Field(default_factory=dict)
    sub_tasks: list[str] = Field(default_factory=list)
    passages: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    retrieval_errors: dict[str, str] = Field(default_factory=dict)
    search_queries: dict[str, str] = Field(default_factory=dict)
    feature_metrics: dict[str, Any] = Field(default_factory=dict)
    output: Optional[BenchmarkOutput] = None
