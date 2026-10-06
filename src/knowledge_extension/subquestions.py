"""Turn knowledge-extension facets and lemmas into retrieval sub-questions."""

from __future__ import annotations

import json
from typing import Any

import dspy

from src.schemas.slice import ComparisonSlice

_MAX_FACETS = 6
_MAX_LEMMAS = 3


class FacetLemmaSubquestions(dspy.Signature):
    """Write one focused sub-question per thematic facet and lemma, for each slice."""

    query: str = dspy.InputField()
    concept: str = dspy.InputField()
    slices: str = dspy.InputField(desc="JSON list of comparison slices")
    thematic_facets: str = dspy.InputField(desc="JSON list of facet terms")
    lemmas_by_slice: str = dspy.InputField(desc="JSON object of slice_id to lemma lists")
    subquestions: list[str] = dspy.OutputField(
        desc="Short questions that mention a facet or lemma and a slice label"
    )


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _lemma_map(expansion: dict[str, Any], slices: list[ComparisonSlice]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for slice_ in slices:
        words = expansion.get(slice_.slice_id) or []
        mapping[slice_.slice_id] = _unique([str(word) for word in words])[:_MAX_LEMMAS]
    return mapping


def heuristic_subquestions(
    concept: str,
    slices: list[ComparisonSlice],
    expansion: dict[str, Any],
) -> list[dict[str, str]]:
    """Deterministic sub-questions from facets and per-slice lemmas."""
    subject = (concept or "the subject").strip() or "the subject"
    facets = _unique([str(item) for item in (expansion.get("thematic_facets") or [])])[:_MAX_FACETS]
    lemmas = _lemma_map(expansion, slices)
    items: list[dict[str, str]] = []
    index = 1
    for slice_ in slices:
        for facet in facets:
            items.append(
                {
                    "id": f"sq_{index}",
                    "slice_id": slice_.slice_id,
                    "source": "facet",
                    "term": facet,
                    "question": f"How is {facet} described for {subject} in {slice_.label}?",
                }
            )
            index += 1
        for lemma in lemmas.get(slice_.slice_id) or []:
            if lemma.lower() == subject.lower():
                continue
            items.append(
                {
                    "id": f"sq_{index}",
                    "slice_id": slice_.slice_id,
                    "source": "lemma",
                    "term": lemma,
                    "question": f"What does {lemma} mean for {subject} in {slice_.label}?",
                }
            )
            index += 1
    if len(slices) >= 2 and facets:
        labels = " and ".join(slice_.label for slice_ in slices)
        items.append(
            {
                "id": f"sq_{index}",
                "slice_id": "",
                "source": "contrast",
                "term": facets[0],
                "question": f"How does {facets[0]} for {subject} differ across {labels}?",
            }
        )
    return items


def _parse_questions(value: Any) -> list[str]:
    if isinstance(value, list):
        return _unique([str(item) for item in value])
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return _unique([str(item) for item in parsed])
    return []


def _attach_model_questions(
    fallback: list[dict[str, str]],
    questions: list[str],
    slices: list[ComparisonSlice],
) -> list[dict[str, str]]:
    if len(questions) < 2:
        return fallback
    by_slice = {slice_.slice_id: slice_ for slice_ in slices}
    labels = [(slice_.slice_id, slice_.label.lower()) for slice_ in slices]
    merged: list[dict[str, str]] = []
    for index, question in enumerate(questions, start=1):
        haystack = question.lower()
        slice_id = ""
        for identifier, label in labels:
            if label and label in haystack:
                slice_id = identifier
                break
        merged.append(
            {
                "id": f"sq_{index}",
                "slice_id": slice_id,
                "source": "model",
                "term": by_slice[slice_id].label if slice_id in by_slice else "",
                "question": question,
            }
        )
    return merged


def generate_facet_lemma_subquestions(
    query: str,
    concept: str,
    slices: list[ComparisonSlice],
    expansion: dict[str, Any],
) -> list[dict[str, str]]:
    """Build sub-questions from thematic facets and lemmas. Uses DSPy when an LM is set."""
    fallback = heuristic_subquestions(concept, slices, expansion)
    if getattr(dspy.settings, "lm", None) is None:
        return fallback
    lemmas = _lemma_map(expansion, slices)
    facets = _unique([str(item) for item in (expansion.get("thematic_facets") or [])])[:_MAX_FACETS]
    try:
        prediction = dspy.Predict(FacetLemmaSubquestions)(
            query=query,
            concept=concept,
            slices=json.dumps([slice_.model_dump() for slice_ in slices]),
            thematic_facets=json.dumps(facets),
            lemmas_by_slice=json.dumps(lemmas),
        )
    except Exception:
        return fallback
    return _attach_model_questions(fallback, _parse_questions(getattr(prediction, "subquestions", None)), slices)


def subquestion_texts(items: list[dict[str, str]]) -> list[str]:
    return [str(item.get("question") or "") for item in items if item.get("question")]
