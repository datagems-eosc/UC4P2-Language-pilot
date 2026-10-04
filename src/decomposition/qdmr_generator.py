"""Compatibility wrapper. The pipeline stores each step's ``#k`` instruction."""

from __future__ import annotations

from src.decomposition.base import build_comparative_steps
from src.decomposition.factory import QDMRDecomposerFactory
from src.schemas.slice import ComparisonSlice


def generate_subtasks(
    query: str,
    slices: list[ComparisonSlice],
    extended_context: str,
) -> list[str]:
    """Deterministic instructions, independent of the selected backend."""
    return [
        step.instruction
        for step in build_comparative_steps(query, slices, extended_context)
    ]


def decompose_question(
    query: str,
    slices: list[ComparisonSlice],
    extended_context: str,
) -> list[str]:
    """Decompose with the configured backend and return ``#k`` instructions."""
    steps = QDMRDecomposerFactory.create().decompose(query, slices, extended_context)
    return [step.instruction for step in steps]
