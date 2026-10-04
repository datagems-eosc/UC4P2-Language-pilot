"""Facet, lemma, and feature-lens expansion across every comparison slice."""

from __future__ import annotations

import json
import re
from typing import Any

import dspy

from src.schemas.slice import ComparisonSlice

_MARRIAGE_FACETS = [
    "husband",
    "wife",
    "divorce",
    "dowry",
    "property ownership",
    "spousal duties",
]
_MARRIAGE_LENSES = ["legal_standing", "economic_contract", "social_stance"]
_US_LENSES = ["social_stance", "political_framing", "national_identity"]
_US_GERMAN = ["Amerika", "Vereinigte Staaten", "Nordamerika"]
_MARRIAGE_1800_ENGLISH = ["coverture", "matrimony", "common-law"]


class KnowledgeExtension(dspy.Signature):
    """Expand a concept into facets, per-slice lemmas, and comparative lenses."""

    query: str = dspy.InputField()
    slices: str = dspy.InputField(desc="JSON list of comparison slices")
    thematic_facets: list[str] = dspy.OutputField(desc="Thematic and facet terms")
    slice_lexical_variants: dict[str, list[str]] = dspy.OutputField(
        desc="Language- and period-specific variants keyed by slice_id"
    )
    feature_lenses: list[str] = dspy.OutputField(desc="Two to four comparative metrics")


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _is_us(concept: str, query: str) -> bool:
    return bool(re.search(r"\b(US|U\.S\.|USA|United States|America)\b", f"{concept} {query}"))


def _language(slice_: ComparisonSlice) -> str:
    if slice_.language and slice_.language.lower() not in {"unspecified", "english"}:
        return slice_.language
    return "English"


def variants_for_slice(query: str, concept: str, slice_: ComparisonSlice) -> list[str]:
    """Period- and language-accurate lemmas for one slice."""
    language = _language(slice_)
    if "marriage" in concept.lower() or re.search(r"\bmarriage\b", query, re.I):
        if language == "German":
            return ["Ehe", "Gattin", "Mitgift"]
        if slice_.period_start < 1900:
            return list(_MARRIAGE_1800_ENGLISH)
        return ["marriage", "spouse", "partnership"]
    if _is_us(concept, query):
        if language == "German":
            return list(_US_GERMAN)
        return ["United States", "America", "the Union"]
    return [concept]


def heuristic_expansion(
    query: str,
    concept: str,
    slices: list[ComparisonSlice],
) -> dict[str, Any]:
    """Lexicon used when no language model is configured or the model call fails."""
    facets: list[str] = []
    lenses: list[str] = []
    if "marriage" in concept.lower() or re.search(r"\bmarriage\b", query, re.I):
        facets.extend(_MARRIAGE_FACETS)
        lenses.extend(_MARRIAGE_LENSES)
    if _is_us(concept, query):
        lenses.extend(_US_LENSES)
        if concept not in facets:
            facets.append(concept)
    if not facets:
        facets.append(concept)
    if len(lenses) < 2:
        lenses.extend(["social_stance", "topical_focus"])
    variants = {
        slice_.slice_id: variants_for_slice(query, concept, slice_) for slice_ in slices
    }
    flat: dict[str, list[str]] = {
        "thematic_facets": _unique(facets),
        "feature_lenses": _unique(lenses)[:4],
    }
    for slice_id, words in variants.items():
        flat[slice_id] = _unique(words)
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
    for slice_ in slices:
        words = variants.get(slice_.slice_id) or merged.get(slice_.slice_id) or []
        merged[slice_.slice_id] = _unique([str(item) for item in words])
    return merged
