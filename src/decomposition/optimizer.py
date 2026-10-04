"""MIPROv2 compilation for the advanced QDMR decomposer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import dspy

from src.decomposition.advanced_dspy_module import AdvancedQDMRDecomposer
from src.decomposition.validation import validate_qdmr_graph


def qdmr_quality_metric(gold: Any, pred: Any, trace: Any = None) -> float:
    """Score structural validity and optional gold overlap."""
    del trace
    predicted = str(
        getattr(pred, "qdmr_string", None)
        or getattr(pred, "decomposition", None)
        or pred
        or ""
    ).strip()
    gold_text = str(
        getattr(gold, "qdmr_string", None)
        or getattr(gold, "decomposition", None)
        or getattr(gold, "qdmr", None)
        or ""
    ).strip()
    min_steps = 2
    gold_valid, _ = validate_qdmr_graph(gold_text, expected_min_steps=2) if gold_text else (False, "")
    if gold_text and gold_valid:
        min_steps = max(2, gold_text.count(";") + 1)
    valid, _ = validate_qdmr_graph(predicted, expected_min_steps=min_steps)
    if not valid:
        return 0.0
    score = 0.6
    if gold_text:
        gold_refs = gold_text.count("#")
        pred_refs = predicted.count("#")
        if gold_refs == 0:
            score += 0.2
        else:
            score += 0.2 * min(1.0, pred_refs / max(gold_refs, 1))
        gold_ops = sum(token in gold_text.lower() for token in ("return", "compare"))
        pred_ops = sum(token in predicted.lower() for token in ("return", "compare"))
        score += 0.2 * (1.0 if pred_ops >= max(gold_ops, 1) else 0.5)
    else:
        score += 0.4
    return float(min(score, 1.0))


def compile_qdmr_engine(
    trainset: list[dspy.Example],
    output_path: str = "artifacts/compiled_qdmr.json",
    *,
    valset: list[dspy.Example] | None = None,
    auto: str = "light",
    num_candidates: int = 5,
    student: AdvancedQDMRDecomposer | None = None,
) -> AdvancedQDMRDecomposer:
    """Compile ``AdvancedQDMRDecomposer`` with MIPROv2 and save weights."""
    from dspy.teleprompt import MIPROv2

    wrapper = student or AdvancedQDMRDecomposer()
    program = wrapper.program
    teleprompter = MIPROv2(
        metric=qdmr_quality_metric,
        auto=auto,  # type: ignore[arg-type]
        num_candidates=num_candidates,
    )
    compiled_program = teleprompter.compile(
        program,
        trainset=trainset,
        valset=valset,
        requires_permission_to_run=False,
    )
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    compiled_program.save(str(destination))
    wrapper.program = compiled_program
    return wrapper


def load_compiled_decomposer(
    weights_path: str = "artifacts/compiled_qdmr.json",
) -> AdvancedQDMRDecomposer:
    """Load a compiled advanced decomposer from disk."""
    module = AdvancedQDMRDecomposer()
    path = Path(weights_path)
    if not path.is_file():
        raise FileNotFoundError(f"Compiled QDMR weights not found: {weights_path}")
    module.load(str(path))
    return module
