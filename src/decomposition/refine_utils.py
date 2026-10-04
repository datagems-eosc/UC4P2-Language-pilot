"""Helpers that keep Break structure while polishing DSPy wording."""

from __future__ import annotations

import re

from src.decomposition.base import (
    QDMRStep,
    ensure_synthesize_root,
    looks_like_synthesize,
    reference_ids,
    steps_are_valid,
)
from src.schemas.slice import ComparisonSlice

_YEAR = re.compile(r"\b(1[8-9]\d{2}|20\d{2})\b")
_WORD = re.compile(r"[a-z0-9]+", re.I)


def step_body(step: QDMRStep) -> str:
    prefix = f"#{step.step_index} "
    text = step.instruction.strip()
    if text.startswith(prefix):
        return text[len(prefix) :].strip()
    if step.arguments:
        return str(step.arguments[0]).strip()
    return text


def is_telegraphic(body: str) -> bool:
    """True for short Break-style phrases that are not full sub-questions."""
    text = body.strip()
    if not text:
        return True
    if not text.endswith("?"):
        return True
    words = text.split()
    if len(words) <= 4 and not re.match(
        r"(?i)^(how|what|which|who|when|where|why)\b", text
    ):
        return True
    return False


def _rebuild(step_index: int, body: str, references: list[int]) -> QDMRStep:
    text = body.strip()
    if text and not text.endswith("?"):
        text = text.rstrip(".") + "?"
    return QDMRStep(
        step_index=step_index,
        operator="return",
        arguments=[text],
        references=list(references),
        instruction=f"#{step_index} {text}",
    )


def expand_telegraphic_body(
    body: str,
    *,
    concept: str,
    slices: list[ComparisonSlice],
    step: QDMRStep,
) -> str:
    """Turn a Break fragment into a readable sub-question."""
    subject = concept.strip() or "the subject"
    text = body.strip()
    if not text or text.casefold() in {subject.casefold(), "the subject"}:
        return f"How is {subject} defined?"
    year = _YEAR.search(text)
    if year:
        return f"How is {subject} described in {year.group(1)}?"
    if len(slices) >= step.step_index:
        label = slices[step.step_index - 1].label
        if label and label in text:
            return f"How is {subject} described in {label}?"
    cleaned = re.sub(r"#\d+", "", text).strip(" ;,.")
    if step.references and cleaned:
        return f"What is meant by {cleaned}?"
    if cleaned:
        if re.match(r"(?i)^(how|what|which|who|when|where|why)\b", cleaned):
            return cleaned if cleaned.endswith("?") else cleaned + "?"
        return f"What is {cleaned}?"
    if step.references:
        refs = ", ".join(f"#{ref}" for ref in step.references)
        return f"How does {subject} relate to {refs}?"
    return f"How is {subject} described?"


def normalize_break_steps(
    steps: list[QDMRStep],
    *,
    concept: str = "",
    slices: list[ComparisonSlice] | None = None,
) -> list[QDMRStep]:
    """Make Break drafts readable and end in a synthesize node."""
    if not steps:
        return steps
    slices = slices or []
    polished: list[QDMRStep] = []
    for step in steps:
        body = step_body(step)
        if looks_like_synthesize(step):
            polished.append(step)
            continue
        if is_telegraphic(body):
            body = expand_telegraphic_body(
                body, concept=concept, slices=slices, step=step
            )
        polished.append(_rebuild(step.step_index, body, step.references))
    return ensure_synthesize_root(polished)


def _with_references(body: str, references: list[int]) -> str:
    """Keep the Break citations visible in the rewritten wording."""
    text = body.strip()
    if not references:
        return text
    present = set(reference_ids(text))
    if set(references).issubset(present):
        return text
    refs = ", ".join(f"#{ref}" for ref in references)
    base = text.rstrip(" ?.")
    return f"{base}, given {refs}?"


def transfer_break_structure(
    draft: list[QDMRStep],
    rewritten: list[QDMRStep],
) -> list[QDMRStep]:
    """Always keep the Break ``#k`` graph; only borrow DSPy wording.

    DSPy often returns a flat list of gold-style questions and drops the
    Break edges. The Break step count and references are the structure we
    keep. Rewritten bodies are matched onto those nodes when possible.
    """
    draft = ensure_synthesize_root(draft)
    rewritten = ensure_synthesize_root(rewritten)
    draft_content = draft[:-1]
    rewritten_content = rewritten[:-1]
    used: set[int] = set()
    merged: list[QDMRStep] = []
    for position, draft_step in enumerate(draft_content):
        body = step_body(draft_step)
        best_index = None
        best_score = -1.0
        for index, rewritten_step in enumerate(rewritten_content):
            if index in used:
                continue
            score = jaccard(step_body(draft_step), step_body(rewritten_step))
            if index == position:
                score += 0.15
            if score > best_score:
                best_score = score
                best_index = index
        if best_index is not None and best_score >= 0.05:
            candidate = step_body(rewritten_content[best_index])
            if not is_telegraphic(candidate):
                body = candidate
                used.add(best_index)
        body = _with_references(body, draft_step.references)
        merged.append(
            _rebuild(draft_step.step_index, body, draft_step.references)
        )
    return ensure_synthesize_root(merged)


def format_edges(steps: list[QDMRStep]) -> str:
    """Compact dependency summary for notebook inspection."""
    parts: list[str] = []
    for step in steps:
        if not step.references:
            parts.append(f"#{step.step_index}")
            continue
        refs = ",".join(f"#{ref}" for ref in step.references)
        parts.append(f"#{step.step_index}←{refs}")
    return "  ".join(parts)


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _WORD.findall(text) if len(token) > 2}


def jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_against_gold(gold: list[QDMRStep], predicted: list[QDMRStep]) -> dict[str, float | bool | int]:
    """Small metric for notebook comparisons."""
    predicted = ensure_synthesize_root(predicted)
    gold_bodies = [step_body(step) for step in gold if not looks_like_synthesize(step)]
    pred_bodies = [
        step_body(step) for step in predicted if not looks_like_synthesize(step)
    ]
    pairs = list(zip(gold_bodies, pred_bodies))
    overlap = sum(jaccard(left, right) for left, right in pairs) / max(len(pairs), 1)
    last = predicted[-1]
    synthesize_ok = looks_like_synthesize(last) and set(last.references) >= set(
        range(1, last.step_index)
    )
    valid = steps_are_valid(predicted)
    step_match = len(gold) == len(predicted)
    score = (
        0.35 * float(valid)
        + 0.25 * float(synthesize_ok)
        + 0.15 * float(step_match)
        + 0.25 * overlap
    )
    return {
        "valid": valid,
        "synthesize": synthesize_ok,
        "step_count_match": step_match,
        "gold_steps": len(gold),
        "pred_steps": len(predicted),
        "text_overlap": round(overlap, 3),
        "score": round(score, 3),
    }


def nearest_items(
    items: list[dict],
    *,
    asked_question: str,
    concept: str,
    years: list[int],
    limit: int = 2,
) -> list[dict]:
    """Pick the closest benchmark examples by year count and question text."""

    def key(item: dict) -> tuple:
        year_gap = abs(len(item["years"]) - len(years))
        concept_gap = 0 if item["concept"].casefold() == concept.casefold() else 1
        overlap = jaccard(asked_question, item["question"])
        return (year_gap, concept_gap, -overlap)

    ranked = sorted(items, key=key)
    return ranked[: max(0, limit)]
