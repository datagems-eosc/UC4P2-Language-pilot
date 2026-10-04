"""Keyword-in-context, collocations, and per-slice feature metrics."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

_STOP = {
    "the",
    "a",
    "an",
    "of",
    "and",
    "or",
    "to",
    "in",
    "on",
    "for",
    "with",
    "by",
    "from",
    "as",
    "at",
    "is",
    "was",
    "were",
    "be",
}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]*", text)


def extract_kwic(passages: list[str], keywords: list[str], window: int = 5) -> list[str]:
    """Return Keyword-In-Context lines around any keyword."""
    snippets: list[str] = []
    needles = [keyword.lower() for keyword in keywords if keyword.strip()]
    for passage in passages:
        tokens = passage.split()
        for index, token in enumerate(tokens):
            folded = token.lower().strip(".,;:\"'")
            if not any(needle == folded or needle in folded for needle in needles):
                continue
            left = tokens[max(0, index - window) : index]
            right = tokens[index + 1 : index + 1 + window]
            snippets.append(" ".join([*left, token, *right]))
    return snippets


def compute_collocations(passages: list[str], target_word: str, top_k: int = 5) -> dict[str, int]:
    """Count words that occur beside ``target_word``."""
    counts: Counter[str] = Counter()
    needle = target_word.lower()
    for passage in passages:
        tokens = _tokens(passage)
        for index, token in enumerate(tokens):
            if needle not in token.lower():
                continue
            neighbors = tokens[max(0, index - 2) : index] + tokens[index + 1 : index + 3]
            for neighbor in neighbors:
                lowered = neighbor.lower()
                if lowered in _STOP or lowered == needle:
                    continue
                counts[lowered] += 1
    return dict(counts.most_common(top_k))


def compute_feature_metrics(
    slice_passages: dict[str, list[str]],
    feature_lenses: list[str],
) -> dict[str, Any]:
    """KWIC, collocations, and a simple stance count for every slice and lens."""
    metrics: dict[str, Any] = {}
    stance_terms = ["right", "duty", "love", "law", "property", "equal"]
    for slice_id, passages in slice_passages.items():
        slice_metrics: dict[str, Any] = {"passage_count": len(passages)}
        joined = passages
        for lens in feature_lenses:
            keywords = [part for part in re.split(r"[_\s/]+", lens) if part]
            keywords.append(lens.replace("_", " "))
            slice_metrics[lens] = {
                "kwic": extract_kwic(joined, keywords, window=5)[:5],
                "collocations": compute_collocations(joined, keywords[0], top_k=5)
                if keywords
                else {},
            }
        stance = Counter()
        blob = " ".join(joined).lower()
        for term in stance_terms:
            stance[term] = len(re.findall(rf"\b{re.escape(term)}\b", blob))
        slice_metrics["stance_distribution"] = dict(stance)
        metrics[slice_id] = slice_metrics
    return metrics
