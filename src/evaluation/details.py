"""Per-metric calculation elements for NLG scores (hypothesis vs reference)."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from src.evaluation.nlg import (
    _f1,
    _lcs_length,
    _ngrams,
    _normalize,
    _precision,
    _tokens,
    strip_citation_marks,
)


def _element(eid: str, label: str, value: Any, *, unit: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"id": eid, "label": label, "value": value}
    if unit is not None:
        item["unit"] = unit
    return item


def _counter_map(counter: Counter) -> dict[str, int]:
    return {" ".join(gram) if isinstance(gram, tuple) else str(gram): int(count) for gram, count in counter.items()}


def nlg_metrics_with_details(hypothesis: str, reference: str) -> dict[str, Any]:
    """Return flat metric values plus calculation elements for each score."""
    cleaned = strip_citation_marks(hypothesis)
    hyp = _tokens(cleaned)
    ref = _tokens(reference)
    hyp_norm = _normalize(cleaned)
    ref_norm = _normalize(reference)

    details: dict[str, dict[str, Any]] = {}
    metrics: dict[str, float] = {}

    exact = 1.0 if hyp_norm == ref_norm else 0.0
    metrics["exact_match"] = exact
    details["exact_match"] = {
        "value": exact,
        "formula": "1 if normalize(strip_citations(hyp)) == normalize(ref) else 0",
        "elements": [
            _element("hypothesis_raw", "Hypothesis (raw synthesized answer)", hypothesis),
            _element("hypothesis_cleaned", "Hypothesis after stripping [ref_N]", cleaned),
            _element("hypothesis_normalized", "Normalized hypothesis", hyp_norm),
            _element("reference_raw", "Reference (ground truth)", reference),
            _element("reference_normalized", "Normalized reference", ref_norm),
            _element("equal", "Normalized strings equal", hyp_norm == ref_norm),
        ],
    }

    hyp_bag = Counter(hyp)
    ref_bag = Counter(ref)
    overlap = sum(min(count, ref_bag[token]) for token, count in hyp_bag.items())
    hyp_total = sum(hyp_bag.values())
    ref_total = sum(ref_bag.values())
    token_p = overlap / hyp_total if hyp_bag else 0.0
    token_r = overlap / ref_total if ref_bag else 0.0
    token_f = _f1(token_p, token_r)
    metrics["token_precision"] = round(token_p, 4)
    metrics["token_recall"] = round(token_r, 4)
    metrics["token_f1"] = round(token_f, 4)
    token_elements = [
        _element("hypothesis_tokens", "Hypothesis token multiset", _counter_map(hyp_bag)),
        _element("reference_tokens", "Reference token multiset", _counter_map(ref_bag)),
        _element("hypothesis_token_count", "|hyp|", hyp_total),
        _element("reference_token_count", "|ref|", ref_total),
        _element("overlap_count", "Clipped unigram overlap", overlap),
        _element("precision", "overlap / |hyp|", round(token_p, 4)),
        _element("recall", "overlap / |ref|", round(token_r, 4)),
        _element("f1", "2PR/(P+R)", round(token_f, 4)),
    ]
    details["token_precision"] = {
        "value": metrics["token_precision"],
        "formula": "overlap / |hyp_tokens|",
        "elements": token_elements,
    }
    details["token_recall"] = {
        "value": metrics["token_recall"],
        "formula": "overlap / |ref_tokens|",
        "elements": token_elements,
    }
    details["token_f1"] = {
        "value": metrics["token_f1"],
        "formula": "2 * P * R / (P + R)",
        "elements": token_elements,
    }

    precisions: list[float] = []
    ngram_elements: list[dict[str, Any]] = [
        _element("hypothesis_tokens", "Hypothesis tokens", hyp),
        _element("reference_tokens", "Reference tokens", ref),
        _element("hypothesis_length", "|hyp|", len(hyp)),
        _element("reference_length", "|ref|", len(ref)),
    ]
    for size in range(1, 5):
        hyp_grams = _ngrams(hyp, size)
        ref_grams = _ngrams(ref, size)
        precision = _precision(hyp_grams, ref_grams) if hyp_grams else 0.0
        precisions.append(precision)
        overlap_n = sum(min(count, ref_grams[gram]) for gram, count in hyp_grams.items())
        ngram_elements.extend(
            [
                _element(f"hyp_{size}grams", f"Hypothesis {size}-grams", _counter_map(hyp_grams)),
                _element(f"ref_{size}grams", f"Reference {size}-grams", _counter_map(ref_grams)),
                _element(f"overlap_{size}grams", f"Clipped {size}-gram overlap", overlap_n),
                _element(f"precision_{size}", f"p_{size}", round(precision, 4)),
            ]
        )
        metrics[f"bleu_{size}"] = round(precision, 4)
        details[f"bleu_{size}"] = {
            "value": metrics[f"bleu_{size}"],
            "formula": f"clipped_overlap({size}-grams) / |hyp {size}-grams|",
            "elements": [
                _element(f"hyp_{size}grams", f"Hypothesis {size}-grams", _counter_map(hyp_grams)),
                _element(f"ref_{size}grams", f"Reference {size}-grams", _counter_map(ref_grams)),
                _element(f"overlap_{size}grams", f"Clipped {size}-gram overlap", overlap_n),
                _element(f"hyp_{size}gram_count", f"|hyp {size}-grams|", sum(hyp_grams.values())),
                _element("precision", f"p_{size}", round(precision, 4)),
            ],
        }

    clipped = [max(item, 1e-9) if hyp else 0.0 for item in precisions]
    if not hyp or not ref or any(item <= 0 for item in precisions):
        geo = 0.0
    else:
        geo = math.exp(sum(math.log(item) for item in clipped) / 4)
    bp = 1.0 if len(hyp) >= len(ref) else (math.exp(1 - len(ref) / len(hyp)) if hyp else 0.0)
    bleu = bp * geo
    metrics["brevity_penalty"] = round(bp, 4)
    metrics["bleu"] = round(bleu, 4)
    bleu_elements = ngram_elements + [
        _element("geometric_mean", "exp(mean(log p_n))", round(geo, 4)),
        _element("brevity_penalty", "BP", round(bp, 4)),
        _element("bleu", "BP * geometric_mean", round(bleu, 4)),
    ]
    details["brevity_penalty"] = {
        "value": metrics["brevity_penalty"],
        "formula": "1 if |hyp| >= |ref| else exp(1 - |ref|/|hyp|)",
        "elements": [
            _element("hypothesis_length", "|hyp|", len(hyp)),
            _element("reference_length", "|ref|", len(ref)),
            _element("brevity_penalty", "BP", round(bp, 4)),
        ],
    }
    details["bleu"] = {
        "value": metrics["bleu"],
        "formula": "BP * exp(mean(log p_n)) for n=1..4",
        "elements": bleu_elements,
    }

    for size, name in ((1, "rouge1"), (2, "rouge2")):
        hyp_grams = _ngrams(hyp, size)
        ref_grams = _ngrams(ref, size)
        overlap_r = sum(min(count, ref_grams[gram]) for gram, count in hyp_grams.items())
        precision = overlap_r / sum(hyp_grams.values()) if hyp_grams else 0.0
        recall = overlap_r / sum(ref_grams.values()) if ref_grams else 0.0
        f1 = _f1(precision, recall)
        metrics[f"{name}_precision"] = round(precision, 4)
        metrics[f"{name}_recall"] = round(recall, 4)
        metrics[f"{name}_f1"] = round(f1, 4)
        elements = [
            _element("hypothesis_grams", f"Hypothesis {size}-grams", _counter_map(hyp_grams)),
            _element("reference_grams", f"Reference {size}-grams", _counter_map(ref_grams)),
            _element("overlap_count", "Clipped overlap", overlap_r),
            _element("hypothesis_gram_count", "|hyp grams|", sum(hyp_grams.values())),
            _element("reference_gram_count", "|ref grams|", sum(ref_grams.values())),
            _element("precision", "P", round(precision, 4)),
            _element("recall", "R", round(recall, 4)),
            _element("f1", "2PR/(P+R)", round(f1, 4)),
        ]
        details[f"{name}_precision"] = {
            "value": metrics[f"{name}_precision"],
            "formula": "clipped_overlap / |hyp grams|",
            "elements": elements,
        }
        details[f"{name}_recall"] = {
            "value": metrics[f"{name}_recall"],
            "formula": "clipped_overlap / |ref grams|",
            "elements": elements,
        }
        details[f"{name}_f1"] = {
            "value": metrics[f"{name}_f1"],
            "formula": "F1 of clipped n-gram overlap",
            "elements": elements,
        }

    lcs = _lcs_length(hyp, ref)
    rouge_l_p = lcs / len(hyp) if hyp else 0.0
    rouge_l_r = lcs / len(ref) if ref else 0.0
    rouge_l_f = _f1(rouge_l_p, rouge_l_r)
    metrics["rougeL_precision"] = round(rouge_l_p, 4)
    metrics["rougeL_recall"] = round(rouge_l_r, 4)
    metrics["rougeL_f1"] = round(rouge_l_f, 4)
    rouge_l_elements = [
        _element("hypothesis_tokens", "Hypothesis tokens", hyp),
        _element("reference_tokens", "Reference tokens", ref),
        _element("lcs_length", "Longest common subsequence length", lcs),
        _element("hypothesis_length", "|hyp|", len(hyp)),
        _element("reference_length", "|ref|", len(ref)),
        _element("precision", "LCS/|hyp|", round(rouge_l_p, 4)),
        _element("recall", "LCS/|ref|", round(rouge_l_r, 4)),
        _element("f1", "2PR/(P+R)", round(rouge_l_f, 4)),
    ]
    details["rougeL_precision"] = {
        "value": metrics["rougeL_precision"],
        "formula": "LCS_length / |hyp_tokens|",
        "elements": rouge_l_elements,
    }
    details["rougeL_recall"] = {
        "value": metrics["rougeL_recall"],
        "formula": "LCS_length / |ref_tokens|",
        "elements": rouge_l_elements,
    }
    details["rougeL_f1"] = {
        "value": metrics["rougeL_f1"],
        "formula": "F1 with P = LCS/|hyp|, R = LCS/|ref|",
        "elements": rouge_l_elements,
    }

    if not hyp or not ref:
        meteor = 0.0
        meteor_elements = [
            _element("hypothesis_tokens", "Hypothesis tokens", hyp),
            _element("reference_tokens", "Reference tokens", ref),
            _element("matches", "Aligned unigram matches", 0),
            _element("meteor", "METEOR", 0.0),
        ]
    elif hyp == ref:
        meteor = 1.0
        meteor_elements = [
            _element("hypothesis_tokens", "Hypothesis tokens", hyp),
            _element("reference_tokens", "Reference tokens", ref),
            _element("identical", "Token sequences identical", True),
            _element("meteor", "METEOR", 1.0),
        ]
    else:
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
        meteor = fmean * (1 - penalty)
        meteor_elements = [
            _element("hypothesis_tokens", "Hypothesis tokens", hyp),
            _element("reference_tokens", "Reference tokens", ref),
            _element("matched_ref_indices", "Reference indices of matches (order of hyp)", ref_idx),
            _element("matches", "Aligned unigram matches", matches),
            _element("chunks", "Fragmentation chunks", chunks),
            _element("precision", "matches/|hyp|", round(precision, 4)),
            _element("recall", "matches/|ref|", round(recall, 4)),
            _element("fmean", "2PR/(P+R)", round(fmean, 4)),
            _element("penalty", "0.5 * (chunks/matches)^3", round(penalty, 4)),
            _element("meteor", "Fmean * (1 - penalty)", round(meteor, 4)),
        ]
    metrics["meteor"] = round(meteor, 4)
    details["meteor"] = {
        "value": metrics["meteor"],
        "formula": "Fmean * (1 - 0.5 * (chunks/matches)^3)",
        "elements": meteor_elements,
    }

    return {"metrics": metrics, "details": details}


def judge_details(judge: dict[str, Any], *, question: str, gold: str, answer: str) -> dict[str, dict[str, Any]]:
    """Calculation-style elements for LLM-as-judge scores."""
    if not judge or not judge.get("available"):
        reason = (judge or {}).get("reason") or "Judge unavailable"
        stub = {
            "value": None,
            "formula": "Integer 1–5 from judge LLM JSON",
            "elements": [
                _element("available", "Judge available", False),
                _element("reason", "Unavailable reason", reason),
                _element("question", "Question", question),
                _element("gold", "Gold answer", gold),
                _element("answer", "System answer (citations stripped)", answer),
            ],
            "status": "missing",
        }
        return {
            "judge.score": stub,
            "judge.faithfulness": stub,
            "judge.coverage": stub,
        }
    shared = [
        _element("question", "Question", question),
        _element("gold", "Gold answer", gold),
        _element("answer", "System answer (citations stripped)", answer),
        _element("judge_lm", "Judge model", judge.get("judge_lm")),
        _element("pipeline_lm", "Pipeline model", judge.get("pipeline_lm")),
        _element("verdict", "Verdict", judge.get("verdict")),
        _element("rationale", "Rationale", judge.get("rationale")),
        _element("score", "Overall score 1–5", judge.get("score")),
        _element("faithfulness", "Faithfulness 1–5", judge.get("faithfulness")),
        _element("coverage", "Coverage 1–5", judge.get("coverage")),
    ]
    return {
        "judge.score": {
            "value": judge.get("score"),
            "formula": "Integer 1–5 from judge LLM JSON field `score`",
            "elements": shared,
        },
        "judge.faithfulness": {
            "value": judge.get("faithfulness"),
            "formula": "Integer 1–5 from judge LLM JSON field `faithfulness`",
            "elements": shared,
        },
        "judge.coverage": {
            "value": judge.get("coverage"),
            "formula": "Integer 1–5 from judge LLM JSON field `coverage`",
            "elements": shared,
        },
    }
