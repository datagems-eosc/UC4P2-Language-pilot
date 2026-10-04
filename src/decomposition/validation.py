"""Deterministic Break-syntax and reference validation for QDMR graphs."""

from __future__ import annotations

from src.decomposition.base import looks_like_synthesize, reference_ids
from src.decomposition.syntax_parser import parse_decomposition, split_steps


def validate_qdmr_graph(qdmr_str: str, expected_min_steps: int) -> tuple[bool, str]:
    """Validate Break syntax integrity before graph use.

    Checks:
    1. Semicolon-delimited steps and a minimum step count (slices + synthesize).
    2. Every ``#k`` points strictly backward (``k <`` current step index).
    3. No out-of-range or forward references.
    4. The final step is a comparative / synthesize terminus.
    """
    text = (qdmr_str or "").strip()
    if not text:
        return False, "QDMR string is empty."
    if ";" not in text and "\n" not in text and expected_min_steps > 1:
        return False, "QDMR string must separate steps with ';' (or newlines)."

    chunks = split_steps(text)
    if len(chunks) < expected_min_steps:
        return (
            False,
            f"Expected at least {expected_min_steps} steps, found {len(chunks)}.",
        )

    try:
        steps = parse_decomposition(text)
    except Exception as exc:
        return False, f"Break parser failed: {exc}"

    if len(steps) < expected_min_steps:
        return (
            False,
            f"Parsed {len(steps)} steps; need at least {expected_min_steps}.",
        )

    for index, step in enumerate(steps, start=1):
        body = step.arguments[0] if step.arguments else step.instruction
        prefix = f"#{index} "
        if isinstance(body, str) and step.instruction.startswith(prefix):
            body = step.instruction[len(prefix) :]
        for ref in reference_ids(str(body), exclude=index):
            if ref < 1:
                return False, f"Step #{index} has an invalid reference #{ref}."
            if ref >= index:
                return (
                    False,
                    f"Step #{index} has a forward or self reference #{ref}.",
                )
            if ref > len(steps):
                return False, f"Step #{index} references missing step #{ref}."

    last = steps[-1]
    if not looks_like_synthesize(last) and not last.references:
        return (
            False,
            "Final step must compare or synthesize earlier steps "
            "(e.g. differ / contrast / synthesize) and cite #k.",
        )
    if not last.references:
        return False, "Final synthesize step must cite earlier steps as #k."
    return True, ""
