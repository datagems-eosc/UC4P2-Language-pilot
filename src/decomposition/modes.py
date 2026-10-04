"""Prompting style for the DSPy decomposition call."""

from __future__ import annotations

PREDICT = "predict"
COT = "cot"
FEW_SHOT = "few-shot"
DECOMPOSE_MODES = (PREDICT, COT, FEW_SHOT)

_ALIASES = {
    "predict": PREDICT,
    "zero-shot": PREDICT,
    "zeroshot": PREDICT,
    "cot": COT,
    "chain-of-thought": COT,
    "chainofthought": COT,
    "few-shot": FEW_SHOT,
    "few-shots": FEW_SHOT,
    "fewshot": FEW_SHOT,
    "fewshots": FEW_SHOT,
}


def normalize_decompose_mode(value: str | None) -> str:
    """Map API / notebook names onto predict, cot, or few-shot."""
    if value is None or not str(value).strip():
        return FEW_SHOT
    key = str(value).strip().lower().replace("_", "-").replace(" ", "-")
    mode = _ALIASES.get(key)
    if mode is None:
        raise ValueError("decompose_mode must be predict, cot, or few-shot")
    return mode
