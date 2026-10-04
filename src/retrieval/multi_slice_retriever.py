"""Partitioned retrieval across N slices.

``CrossDatasetMultiSliceRetriever`` calls the Cross-Dataset Discovery search API.
``MockMultiSliceRetriever`` returns passages that contain the slice lemmas so tests
and offline runs can exercise the same interface.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from typing import Optional

from pydantic import BaseModel

from src.orchestration.slice_executor import (
    CrossDatasetDiscoveryClient,
    RetrievalAPIError,
    build_search_query,
)
from src.schemas.slice import ComparisonSlice

_SYNTHESIZE = (
    "differ",
    "difference",
    "differences",
    "compare",
    "comparison",
    "contrast",
    "across",
    "synthesize",
)


class RetrievedPassage(BaseModel):
    slice_id: str
    doc_id: str
    text: str
    dataset_id: str = ""
    similarity: Optional[float] = None


def _strip_step_prefix(instruction: str) -> str:
    text = instruction.strip()
    if text.startswith("#"):
        parts = text.split(None, 1)
        return parts[1] if len(parts) == 2 else text
    return text


def _is_synthesize(instruction: str) -> bool:
    lowered = instruction.lower()
    return any(token in lowered for token in _SYNTHESIZE)


def search_query_for_slice(
    concept: str,
    slice_: ComparisonSlice,
    variants: list[str],
    sub_tasks: list[str] | None = None,
) -> str:
    """Prefer the decomposed sub-question for this slice, plus lexical variants."""
    matched = ""
    label = (slice_.label or "").strip().lower()
    language = (slice_.language or "").strip().lower()
    for instruction in sub_tasks or []:
        if _is_synthesize(instruction):
            continue
        body = _strip_step_prefix(instruction)
        haystack = body.lower()
        if label and label in haystack:
            matched = body
            break
        if language and language not in {"unspecified", "english"} and language in haystack:
            matched = body
            break
    if matched:
        parts = [matched, *variants[:4]]
        return " ".join(part for part in parts if part).strip()
    return build_search_query(concept, slice_.label, [], variants)


class MockMultiSliceRetriever:
    """In-memory retriever. Each passage mentions the slice lemmas."""

    def retrieve_slice(
        self,
        concept: str,
        slice_: ComparisonSlice,
        variants: list[str],
    ) -> list[RetrievedPassage]:
        lemmas = ", ".join(variants[:4]) if variants else concept
        text = (
            f"In {slice_.label}, {concept} is discussed through {lemmas}. "
            f"The passage mentions {variants[0] if variants else concept}."
        )
        return [
            RetrievedPassage(
                slice_id=slice_.slice_id,
                doc_id=f"{slice_.slice_id}-doc-1",
                text=text,
            )
        ]

    def retrieve_all(
        self,
        concept: str,
        slices: list[ComparisonSlice],
        variants_by_slice: dict[str, list[str]],
        sub_tasks: list[str] | None = None,
    ) -> tuple[dict[str, list[RetrievedPassage]], dict[str, str], dict[str, str]]:
        passages: dict[str, list[RetrievedPassage]] = {}
        errors: dict[str, str] = {}
        queries: dict[str, str] = {}
        if not slices:
            return passages, errors, queries
        with ThreadPoolExecutor(max_workers=max(1, len(slices))) as pool:
            futures = {
                pool.submit(
                    self.retrieve_slice,
                    concept,
                    slice_,
                    variants_by_slice.get(slice_.slice_id, []),
                ): slice_
                for slice_ in slices
            }
            for future in as_completed(futures):
                slice_ = futures[future]
                variants = variants_by_slice.get(slice_.slice_id, [])
                queries[slice_.slice_id] = search_query_for_slice(
                    concept,
                    slice_,
                    variants,
                    sub_tasks,
                )
                passages[slice_.slice_id] = future.result()
        return passages, errors, queries


class CrossDatasetMultiSliceRetriever:
    """One Cross-Dataset Discovery search per slice, run concurrently."""

    def __init__(self, client: CrossDatasetDiscoveryClient | None = None, k: int = 5):
        self.client = client or CrossDatasetDiscoveryClient()
        self.k = k

    def retrieve_slice(
        self,
        concept: str,
        slice_: ComparisonSlice,
        variants: list[str],
        sub_tasks: list[str] | None = None,
    ) -> list[RetrievedPassage]:
        query = search_query_for_slice(concept, slice_, variants, sub_tasks)
        dataset_ids = [slice_.corpus_id] if slice_.corpus_id else None
        payload = self.client.search(query, k=self.k, dataset_ids=dataset_ids)
        passages: list[RetrievedPassage] = []
        for item in payload.get("results") or []:
            if not isinstance(item, dict):
                continue
            similarity = item.get("similarity")
            passages.append(
                RetrievedPassage(
                    slice_id=slice_.slice_id,
                    doc_id=str(item.get("object_id") or ""),
                    text=str(item.get("content") or ""),
                    dataset_id=str(item.get("dataset_id") or ""),
                    similarity=float(similarity) if similarity is not None else None,
                )
            )
        return passages

    def retrieve_all(
        self,
        concept: str,
        slices: list[ComparisonSlice],
        variants_by_slice: dict[str, list[str]],
        sub_tasks: list[str] | None = None,
    ) -> tuple[dict[str, list[RetrievedPassage]], dict[str, str], dict[str, str]]:
        passages: dict[str, list[RetrievedPassage]] = {}
        errors: dict[str, str] = {}
        queries: dict[str, str] = {}
        if not slices:
            return passages, errors, queries

        def _one(slice_: ComparisonSlice) -> tuple[ComparisonSlice, list[RetrievedPassage] | str]:
            variants = variants_by_slice.get(slice_.slice_id, [])
            try:
                return slice_, self.retrieve_slice(concept, slice_, variants, sub_tasks)
            except RetrievalAPIError as exc:
                return slice_, str(exc)

        with ThreadPoolExecutor(max_workers=max(1, len(slices))) as pool:
            futures = [pool.submit(_one, slice_) for slice_ in slices]
            for future in as_completed(futures):
                slice_, result = future.result()
                variants = variants_by_slice.get(slice_.slice_id, [])
                queries[slice_.slice_id] = search_query_for_slice(
                    concept, slice_, variants, sub_tasks
                )
                if isinstance(result, str):
                    passages[slice_.slice_id] = []
                    errors[slice_.slice_id] = result
                else:
                    passages[slice_.slice_id] = result
        return passages, errors, queries
