"""Facet, lemma, and feature-lens expansion across every comparison slice.

Offline fallback is generic: it uses the query concept and slice metadata only.
Question-specific lexicons (marriage, US, …) are not hardcoded. When an LM is
configured, it proposes facets and period/language lemmas for whatever concept
the question names.
"""

from __future__ import annotations

import json
from typing import Any

import dspy

from src.schemas.slice import ComparisonSlice

# Encyclopedic comparison dimensions. Not tied to a Pilot 2 question.
_GENERIC_FACETS = (
    "definition",
    "origin",
    "attributes",
    "roles or functions",
    "reputation",
)
_GENERIC_LENSES = (
    "definitional_focus",
    "social_stance",
    "topical_focus",
    "institutional_framing",
)


class KnowledgeExtension(dspy.Signature):
    """Expand whatever concept the question names. Do not assume a topic.

    Facets are aspects of this concept (definition, origin, attributes, …).
    Lemmas are how each slice's language and period would name the concept.
    Lenses are two to four comparative angles, not topic-specific word lists.
    """

    query: str = dspy.InputField()
    concept: str = dspy.InputField(desc="Concept extracted from the question")
    slices: str = dspy.InputField(desc="JSON list of comparison slices")
    thematic_facets: list[str] = dspy.OutputField(desc="Thematic aspects of this concept")
    slice_lexical_variants: dict[str, list[str]] = dspy.OutputField(
        desc="Language- and period-specific names for the concept, keyed by slice_id"
    )
    feature_lenses: list[str] = dspy.OutputField(desc="Two to four comparative metrics")


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _language(slice_: ComparisonSlice) -> str:
    if slice_.language and slice_.language.lower() not in {"unspecified", "english"}:
        return slice_.language
    return "English"


def variants_for_slice(query: str, concept: str, slice_: ComparisonSlice) -> list[str]:
    """Generic lemmas: the concept, tagged by this slice's language and period."""
    del query
    subject = (concept or "").strip() or "the subject"
    language = _language(slice_)
    label = (slice_.label or "").strip()
    words = [subject]
    if language and language.lower() != "english":
        words.append(f"{subject} ({language})")
    if label:
        words.append(f"{subject} in {label}")
    return _unique(words)


def heuristic_expansion(
    query: str,
    concept: str,
    slices: list[ComparisonSlice],
) -> dict[str, Any]:
    """Offline expansion when no LM is configured or the model call fails."""
    subject = (concept or "").strip() or "the subject"
    facets = _unique([subject, *_GENERIC_FACETS])
    lenses = list(_GENERIC_LENSES)
    variants = {
        slice_.slice_id: variants_for_slice(query, subject, slice_) for slice_ in slices
    }
    flat: dict[str, list[str]] = {
        "thematic_facets": facets,
        "feature_lenses": lenses[:4],
    }
    for slice_id, words in variants.items():
        flat[slice_id] = words
    flat["_variants"] = variants  # type: ignore[assignment]
    return flat


def knowledge_extension_payload(expansion: dict[str, Any]) -> dict[str, list[str]]:
    """Benchmark view: facets, lenses, and one list of lemmas per slice."""
    payload: dict[str, list[str]] = {}
    for key, value in expansion.items():
        if key.startswith("_"):
            continue
        if isinstance(value, list):
            payload[key] = [str(item) for item in value]
    return payload


def _lm_ready() -> bool:
    return getattr(dspy.settings, "lm", None) is not None


def _parse_json_dict(value: Any) -> dict[str, list[str]]:
    if isinstance(value, dict):
        return {str(key): _unique(list(item)) for key, item in value.items()}
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return {str(key): _unique(list(item)) for key, item in parsed.items()}
    return {}


def expand_knowledge(
    query: str,
    concept: str,
    slices: list[ComparisonSlice],
) -> dict[str, Any]:
    """Expand ``concept`` for every slice. DSPy is used when an LM is configured."""
    fallback = heuristic_expansion(query, concept, slices)
    if not _lm_ready():
        return fallback
    try:
        prediction = dspy.Predict(KnowledgeExtension)(
            query=query,
            concept=concept,
            slices=json.dumps([slice_.model_dump() for slice_ in slices]),
        )
    except Exception:
        return fallback
    facets = getattr(prediction, "thematic_facets", None)
    lenses = getattr(prediction, "feature_lenses", None)
    variants = _parse_json_dict(getattr(prediction, "slice_lexical_variants", None))
    if not isinstance(facets, list) or len(facets) < 1:
        return fallback
    if not isinstance(lenses, list) or len(lenses) < 2:
        return fallback
    merged = heuristic_expansion(query, concept, slices)
    merged["thematic_facets"] = _unique([str(item) for item in facets])
    merged["feature_lenses"] = _unique([str(item) for item in lenses])[:4]
    subject = (concept or "").strip() or "the subject"
    for slice_ in slices:
        words = variants.get(slice_.slice_id) or [subject]
        merged[slice_.slice_id] = _unique([str(item) for item in words]) or [subject]
    return merged
