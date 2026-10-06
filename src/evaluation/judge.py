"""LLM-as-judge for the synthesized answer.

Always calls Scayle, but a different model than the pipeline LM
(default: pipeline ``qwen3``, judge ``glm-5.3-flash``).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from src.llm import chat_completion, credentials_present_for, pipeline_lm_identity

_JSON = re.compile(r"\{.*\}", re.S)
_VERDICTS = {"supported", "partial", "contradicted", "insufficient"}
DEFAULT_SCAYLE_JUDGE_MODEL = "glm-5.3-flash"
FALLBACK_SCAYLE_JUDGE_MODEL = "kimi-k2.6"


def _disabled() -> bool:
    return os.getenv("JUDGE_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def _norm_model(name: str) -> str:
    return re.sub(r"[_\s]+", "-", (name or "").strip().lower())


def _same_model(left: str, right: str) -> bool:
    return bool(left) and _norm_model(left) == _norm_model(right)


def resolve_judge_target() -> tuple[str, str] | None:
    """Scayle + a model that is not the pipeline model."""
    if not credentials_present_for("scayle"):
        return None
    _, pipeline_model = pipeline_lm_identity()
    requested = (
        os.getenv("JUDGE_LLM_MODEL", "").strip()
        or os.getenv("SCAYLE_JUDGE_MODEL_NAME", "").strip()
        or DEFAULT_SCAYLE_JUDGE_MODEL
    )
    model = requested
    if _same_model(model, pipeline_model):
        model = (
            FALLBACK_SCAYLE_JUDGE_MODEL
            if _same_model(model, DEFAULT_SCAYLE_JUDGE_MODEL)
            else DEFAULT_SCAYLE_JUDGE_MODEL
        )
    if _same_model(model, pipeline_model):
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
) -> dict[str, Any]:
    """Score the pipeline answer against gold with a second Scayle model."""
    if _disabled():
        return {"available": False, "reason": "JUDGE_DISABLED is set."}
    pipeline_provider, pipeline_model = pipeline_lm_identity()
    if not credentials_present_for("scayle"):
        return {
            "available": False,
            "reason": "Scayle credentials are required for the judge (SCAYLE_USERNAME / SCAYLE_PASSWORD).",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_model}",
        }
    target = resolve_judge_target()
    if target is None:
        return {
            "available": False,
            "reason": (
                "Judge stays on Scayle but needs another model than "
                f"{pipeline_provider}:{pipeline_model}. Set JUDGE_LLM_MODEL "
                f"(default {DEFAULT_SCAYLE_JUDGE_MODEL})."
            ),
            "pipeline_lm": f"{pipeline_provider}:{pipeline_model}",
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
            "pipeline_lm": f"{pipeline_provider}:{pipeline_model}",
        }
    parsed = _parse_judgment(raw)
    if parsed is None:
        return {
            "available": False,
            "reason": "Judge LLM did not return valid JSON.",
            "judge_lm": f"{provider}:{model}",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_model}",
            "raw": (raw or "")[:500],
        }
    parsed.update(
        {
            "available": True,
            "judge_lm": f"{provider}:{model}",
            "pipeline_lm": f"{pipeline_provider}:{pipeline_model}",
        }
    )
    return parsed
