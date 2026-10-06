"""Compare a synthesized answer to Pilot 2 ground truth with NLG metrics."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.evaluation.judge import judge_synthesized_answer
from src.decomposition.benchmark_fewshots import load_benchmark

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.I)
_REF_MARK = re.compile(r"\[ref_\d+\]")
_SPACE = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD.finditer(text or "")]


def _normalize(text: str) -> str:
    folded = _PUNCT.sub(" ", (text or "").lower())
    return _SPACE.sub(" ", folded).strip()


def strip_citation_marks(text: str) -> str:
    return _SPACE.sub(" ", _REF_MARK.sub(" ", text or "")).strip()


def _ngrams(tokens: list[str], size: int) -> Counter[tuple[str, ...]]:
    if size <= 0 or len(tokens) < size:
        return Counter()
    return Counter(tuple(tokens[index : index + size]) for index in range(len(tokens) - size + 1))


def _precision(hyp: Counter, ref: Counter) -> float:
    if not hyp:
        return 0.0
    overlap = sum(min(count, ref[gram]) for gram, count in hyp.items())
    return overlap / sum(hyp.values())


def bleu_score(hypothesis: str, reference: str, max_n: int = 4) -> dict[str, float]:
    """Sentence BLEU with uniform weights and a brevity penalty."""
    hyp = _tokens(hypothesis)
    ref = _tokens(reference)
    precisions: list[float] = []
    for size in range(1, max_n + 1):
        hyp_grams = _ngrams(hyp, size)
        if not hyp_grams:
            precisions.append(0.0)
            continue
        precisions.append(_precision(hyp_grams, _ngrams(ref, size)))
    clipped = [max(item, 1e-9) if hyp else 0.0 for item in precisions]
    if not hyp or not ref or any(item <= 0 for item in precisions):
        geo = 0.0
    else:
        geo = math.exp(sum(math.log(item) for item in clipped) / max_n)
    bp = 1.0 if len(hyp) >= len(ref) else (math.exp(1 - len(ref) / len(hyp)) if hyp else 0.0)
    scores = {f"bleu_{index}": round(value, 4) for index, value in enumerate(precisions, start=1)}
    scores["bleu"] = round(bp * geo, 4)
    scores["brevity_penalty"] = round(bp, 4)
    return scores


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def rouge_scores(hypothesis: str, reference: str) -> dict[str, float]:
    hyp = _tokens(hypothesis)
    ref = _tokens(reference)
    scores: dict[str, float] = {}
    for size, name in ((1, "rouge1"), (2, "rouge2")):
        hyp_grams = _ngrams(hyp, size)
        ref_grams = _ngrams(ref, size)
        overlap = sum(min(count, ref_grams[gram]) for gram, count in hyp_grams.items())
        precision = overlap / sum(hyp_grams.values()) if hyp_grams else 0.0
        recall = overlap / sum(ref_grams.values()) if ref_grams else 0.0
        scores[f"{name}_precision"] = round(precision, 4)
        scores[f"{name}_recall"] = round(recall, 4)
        scores[f"{name}_f1"] = round(_f1(precision, recall), 4)
    lcs = _lcs_length(hyp, ref)
    precision = lcs / len(hyp) if hyp else 0.0
    recall = lcs / len(ref) if ref else 0.0
    scores["rougeL_precision"] = round(precision, 4)
    scores["rougeL_recall"] = round(recall, 4)
    scores["rougeL_f1"] = round(_f1(precision, recall), 4)
    return scores


def _lcs_length(left: list[str], right: list[str]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for left_token in left:
        current = [0]
        for index, right_token in enumerate(right, start=1):
            if left_token == right_token:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1]


def token_f1(hypothesis: str, reference: str) -> dict[str, float]:
    hyp = Counter(_tokens(hypothesis))
    ref = Counter(_tokens(reference))
    overlap = sum(min(count, ref[token]) for token, count in hyp.items())
    precision = overlap / sum(hyp.values()) if hyp else 0.0
    recall = overlap / sum(ref.values()) if ref else 0.0
    return {
        "token_precision": round(precision, 4),
        "token_recall": round(recall, 4),
        "token_f1": round(_f1(precision, recall), 4),
    }


def meteor_unigram(hypothesis: str, reference: str) -> dict[str, float]:
    """Unigram METEOR-style harmonic mean with a fragmentation penalty."""
    hyp = _tokens(hypothesis)
    ref = _tokens(reference)
    if not hyp or not ref:
        return {"meteor": 0.0}
    if hyp == ref:
        return {"meteor": 1.0}
    ref_positions: dict[str, list[int]] = {}
    for index, token in enumerate(ref):
        ref_positions.setdefault(token, []).append(index)
    remaining = Counter(ref)
    cursor = {token: 0 for token in ref_positions}
    ref_idx: list[int] = []
    for token in hyp:
        slots = ref_positions.get(token) or []
        start = cursor.get(token, 0)
        if start >= len(slots) or remaining[token] <= 0:
            continue
        ref_idx.append(slots[start])
        cursor[token] = start + 1
        remaining[token] -= 1
    matches = len(ref_idx)
    precision = matches / len(hyp)
    recall = matches / len(ref)
    fmean = _f1(precision, recall)
    chunks = 1 if matches else 0
    for left, right in zip(ref_idx, ref_idx[1:]):
        if right != left + 1:
            chunks += 1
    if matches <= 1:
        penalty = 0.0
    else:
        penalty = 0.5 * ((chunks / matches) ** 3)
    return {"meteor": round(fmean * (1 - penalty), 4)}


def nlg_metrics(hypothesis: str, reference: str) -> dict[str, float]:
    cleaned = strip_citation_marks(hypothesis)
    scores = {
        "exact_match": 1.0 if _normalize(cleaned) == _normalize(reference) else 0.0,
    }
    scores.update(token_f1(cleaned, reference))
    scores.update(bleu_score(cleaned, reference))
    scores.update(rouge_scores(cleaned, reference))
    scores.update(meteor_unigram(cleaned, reference))
    return scores


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_STOP = {
    "how",
    "did",
    "does",
    "do",
    "a",
    "an",
    "the",
    "in",
    "of",
    "to",
    "and",
    "or",
    "vs",
    "versus",
    "compared",
    "now",
    "like",
    "over",
    "time",
    "what",
    "which",
    "who",
    "is",
    "are",
    "for",
    "with",
    "from",
    "on",
    "by",
    "across",
    "into",
    "that",
    "this",
    "was",
    "were",
    "about",
    "look",
}
_COMPARATIVE = re.compile(
    r"\b(compared|versus|differ|difference|shift|vary|across time|over time|historical)\b",
    re.I,
)


@lru_cache(maxsize=1)
def _records() -> tuple[dict[str, Any], ...]:
    """Every gold row from JSON files in ``data/`` (Pilot 2 benchmark today)."""
    rows: list[dict[str, Any]] = []
    for path in sorted(_DATA_DIR.glob("*.json")):
        for item in load_benchmark(path):
            if not isinstance(item, dict) or not item.get("Ground_Truth"):
                continue
            row = dict(item)
            row["_source_file"] = path.name
            rows.append(row)
    return tuple(rows)


def _content_tokens(text: str) -> set[str]:
    return {token for token in _tokens(text) if token not in _STOP and len(token) > 2}


def _overlap(left: str, right: str) -> float:
    a = _content_tokens(left)
    b = _content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_parent(item: dict[str, Any]) -> bool:
    return bool(item.get("Subquestion_IDs"))


def _is_benchmark_id(value: str) -> bool:
    return bool(value) and value.isdigit()


def _concept_records(records: tuple[dict[str, Any], ...], concept: str) -> list[dict[str, Any]]:
    folded = _normalize(concept)
    if not folded:
        return []
    return [item for item in records if _normalize(str(item.get("Concept") or "")) == folded]


def _concepts_mentioned(question: str, records: tuple[dict[str, Any], ...]) -> list[str]:
    folded = f" {_normalize(question)} "
    found: list[str] = []
    seen: set[str] = set()
    for item in records:
        concept = str(item.get("Concept") or "").strip()
        key = _normalize(concept)
        if not key or key in seen:
            continue
        if f" {key} " in folded:
            seen.add(key)
            found.append(concept)
    return found


def find_ground_truth(
    question: str,
    query_id: str | None = None,
    concept: str | None = None,
) -> dict[str, Any] | None:
    """Match a gold row from ``data/*.json``.

    Order: Question_ID, exact question text, same Concept (parent row for
    comparative queries), then highest token overlap.
    """
    records = _records()
    wanted_id = str(query_id or "").strip()
    if _is_benchmark_id(wanted_id):
        for item in records:
            if str(item.get("Question_ID") or "") == wanted_id:
                matched = dict(item)
                matched["_match"] = "question_id"
                return matched
    folded = _normalize(question)
    if folded:
        for item in records:
            if _normalize(str(item.get("Question") or "")) == folded:
                matched = dict(item)
                matched["_match"] = "question"
                return matched
    concept_name = (concept or "").strip()
    if not concept_name:
        mentioned = _concepts_mentioned(question, records)
        if len(mentioned) == 1:
            concept_name = mentioned[0]
    pool = _concept_records(records, concept_name) if concept_name else list(records)
    if not pool:
        return None
    if concept_name and _COMPARATIVE.search(question or ""):
        parents = [item for item in pool if _is_parent(item)]
        if len(parents) == 1:
            matched = dict(parents[0])
            matched["_match"] = "concept_parent"
            return matched
        if parents:
            pool = parents
    ranked = sorted(
        pool,
        key=lambda item: _overlap(question, str(item.get("Question") or "")),
        reverse=True,
    )
    best = ranked[0]
    score = _overlap(question, str(best.get("Question") or ""))
    if not concept_name and score < 0.15:
        return None
    matched = dict(best)
    matched["_match"] = "overlap" if score else "concept_parent"
    return matched


def evaluate_against_ground_truth(
    question: str,
    answer: str,
    query_id: str | None = None,
    concept: str | None = None,
) -> dict[str, Any]:
    """Score ``answer`` against gold ``Ground_Truth`` in ``data/*.json``."""
    record = find_ground_truth(question, query_id, concept=concept)
    if record is None:
        return {
            "matched": False,
            "question_id": query_id or "",
            "ground_truth": "",
            "metrics": {},
            "llm_judge": {"available": False, "reason": "No gold answer to judge against."},
            "summary": "No Ground_Truth in data/*.json matched this question, query_id, or concept.",
        }
    gold = str(record.get("Ground_Truth") or "")
    metrics = nlg_metrics(answer, gold)
    question_id = str(record.get("Question_ID") or "")
    judge = judge_synthesized_answer(
        question=question,
        gold=gold,
        answer=strip_citation_marks(answer),
    )
    summary = (
        f"NLG vs {record.get('_source_file')} Question_ID {question_id} "
        f"({record.get('_match')}): ROUGE-L F1 {metrics['rougeL_f1']}, "
        f"BLEU {metrics['bleu']}, token F1 {metrics['token_f1']}, METEOR {metrics['meteor']}."
    )
    if judge.get("available"):
        summary += (
            f" LLM-as-judge {judge.get('judge_lm')} "
            f"score {judge.get('score')}/5 ({judge.get('verdict')})."
        )
    return {
        "matched": True,
        "question_id": question_id,
        "concept": str(record.get("Concept") or ""),
        "gold_question": str(record.get("Question") or ""),
        "gold_source": str(record.get("_source_file") or ""),
        "match": str(record.get("_match") or ""),
        "ground_truth": gold,
        "metrics": metrics,
        "llm_judge": judge,
        "summary": summary,
    }
