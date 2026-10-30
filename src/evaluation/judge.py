"""LLM-as-judge for the synthesized answer.

Always calls Scayle, but a different model than the pipeline LM
(default: pipeline ``qwen3``, judge ``glm-5.3-flash``).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from src.llm import (
    DEFAULT_JUDGE_MODEL,
    chat_completion,
    credentials_present_for,
    default_judge_model,
    default_pipeline_model,
    normalize_model_name,
    pipeline_lm_identity,
)

_JSON = re.compile(r"\{.*\}", re.S)
_VERDICTS = {"supported", "partial", "contradicted", "insufficient"}
FALLBACK_SCAYLE_JUDGE_MODEL = "kimi-k2.6"


def _disabled() -> bool:
    return os.getenv("JUDGE_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def _norm_model(name: str) -> str:
    return re.sub(r"[_\s]+", "-", (name or "").strip().lower())


def _same_model(left: str, right: str) -> bool:
    return bool(left) and _norm_model(left) == _norm_model(right)


def resolve_judge_target(
    *,
    pipeline_model: str | None = None,
    judge_model: str | None = None,
) -> tuple[str, str] | None:
    """Scayle + a model that is not the pipeline model."""
    if not credentials_present_for("scayle"):
        return None
    if pipeline_model:
        pipeline = normalize_model_name(pipeline_model, fallback=default_pipeline_model())
    else:
        _, pipeline = pipeline_lm_identity()
    requested = normalize_model_name(judge_model, fallback=default_judge_model())
    model = requested
    if _same_model(model, pipeline):
        model = (
            FALLBACK_SCAYLE_JUDGE_MODEL
            if _same_model(model, DEFAULT_JUDGE_MODEL)
            else DEFAULT_JUDGE_MODEL
        )
    if _same_model(model, pipeline):
        return None
    return "scayle", model


def _clip_score(value: Any, default: int = 0) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(1, min(5, number)) if number else default


def _parse_judgment(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    match = _JSON.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    verdict = str(payload.get("verdict") or "insufficient").strip().lower()
    if verdict not in _VERDICTS:
        verdict = "insufficient"
    return {
        "score": _clip_score(payload.get("score")),
        "faithfulness": _clip_score(payload.get("faithfulness")),
        "coverage": _clip_score(payload.get("coverage")),
        "verdict": verdict,
        "rationale": str(payload.get("rationale") or "").strip(),
    }


def judge_synthesized_answer(
    question: str,
    gold: str,
    answer: str,
    *,
    pipeline_model: str | None = None,
    judge_model: str | None = None,
) -> dict[str, Any]:
    """Score the pipeline answer against gold with a second Scayle model."""
    if _disabled():
        return {"available": False, "reason": "JUDGE_DISABLED is set."}
    if pipeline_model:
        pipeline_provider, pipeline_name = "scayle", normalize_model_name(
            pipeline_model, fallback=default_pipeline_model()
        )
        # Prefer live DSPy identity when it matches the requested pipeline model.
        live_provider, live_model = pipeline_lm_identity()
        if _same_model(live_model, pipeline_name):
            pipeline_provider, pipeline_name = live_provider, live_model
    else:
        pipeline_provider, pipeline_name = pipeline_lm_identity()
    if not credentials_present_for("scayle"):
        return {
            "available": False,
            "reason": "Scayle credentials are required for the judge (SCAYLE_USERNAME / SCAYLE_PASSWORD).",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_name}",
        }
    target = resolve_judge_target(
        pipeline_model=pipeline_name,
        judge_model=judge_model,
    )
    if target is None:
        return {
            "available": False,
            "reason": (
                "Judge stays on Scayle but needs another model than "
                f"{pipeline_provider}:{pipeline_name}. Set judge_llm_model "
                f"(default {DEFAULT_JUDGE_MODEL})."
            ),
            "pipeline_lm": f"{pipeline_provider}:{pipeline_name}",
        }
    provider, model = target
    prompt = (
        "You are an independent evaluator. The system answer was written by a different model.\n"
        "Compare the system answer to the gold answer for the question.\n"
        "Ignore citation marks such as [ref_1].\n"
        "Return JSON only with keys:\n"
        "  score (1-5 overall quality vs gold),\n"
        "  faithfulness (1-5: no contradictions of gold),\n"
        "  coverage (1-5: gold facts present),\n"
        "  verdict (supported | partial | contradicted | insufficient),\n"
        "  rationale (one or two sentences).\n\n"
        f"Question:\n{question}\n\n"
        f"Gold answer:\n{gold}\n\n"
        f"System answer:\n{answer}\n"
    )
    try:
        raw = chat_completion(
            [
                {
                    "role": "system",
                    "content": "You are an LLM-as-judge. Reply with JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            provider=provider,
            model=model,
        )
    except Exception as exc:
        return {
            "available": False,
            "reason": str(exc),
            "judge_lm": f"{provider}:{model}",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_name}",
        }
    parsed = _parse_judgment(raw)
    if parsed is None:
        return {
            "available": False,
            "reason": "Judge LLM did not return valid JSON.",
            "judge_lm": f"{provider}:{model}",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_name}",
            "raw": (raw or "")[:500],
        }
    parsed.update(
        {
            "available": True,
            "judge_lm": f"{provider}:{model}",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_name}",
        }
    )
    return parsed
