"""Benchmark record for an N-way comparative answer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.schemas.slice import ComparisonSlice


class Citation(BaseModel):
    """One retrieved passage that the answer can point at with [ref_N]."""

    citation_id: str
    slice_id: str
    slice_label: str = ""
    source_document: str
    dataset_id: str = ""
    corpus_name: str = ""
    similarity: float | None = None
    passage_index: int = 0
    text_snippet: str
    used_in_answer: bool = True


class BenchmarkOutput(BaseModel):
    """Serializable answer aligned with the Pilot 2 benchmark record."""

    query_id: str
    question: str
    slices_evaluated: list[ComparisonSlice]
    knowledge_extension: dict[str, list[str]]
    synthesized_answer: str
    feature_metrics: dict[str, Any] = Field(default_factory=dict)
    grounded_citations: list[Citation] = Field(default_factory=list)
