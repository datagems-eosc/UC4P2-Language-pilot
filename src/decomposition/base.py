"""Shared QDMR step model and decomposer interface."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.schemas.slice import ComparisonSlice

_STEP = re.compile(r"^#(\d+)\s+(.*)$", re.S)
_REFERENCE = re.compile(r"#(\d+)")


class QDMRStep(BaseModel):
    """One node in a QDMR decomposition.

    ``instruction`` is the pipeline-facing text (``#k ...``). ``references``
    lists earlier steps this node depends on, in the order they appear.
    """

    step_index: int
    operator: str
    arguments: list[str] = Field(default_factory=list)
    references: list[int] = Field(default_factory=list)
    instruction: str


class BaseQDMRDecomposer(ABC):
    """Generate a typed QDMR plan for an N-slice comparative question."""

    @abstractmethod
    def decompose(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
    ) -> list[QDMRStep]:
        """Return ordered steps. Later steps cite earlier ones via ``#k``."""


def reference_ids(text: str, *, exclude: int | None = None) -> list[int]:
    """Extract ``#k`` identifiers, preserving order and dropping duplicates."""
    found: list[int] = []
    for match in _REFERENCE.finditer(text):
        number = int(match.group(1))
        if number == exclude or number in found:
            continue
        found.append(number)
    return found


def build_comparative_steps(
    query: str,
    slices: list[ComparisonSlice],
    extended_context: str = "",
) -> list[QDMRStep]:
    """Offline plan of sub-questions, one per slice, then a contrast.

    This is used when a backend cannot call a model. It does not insert a
    retrieval step. Later steps cite earlier ones as ``#k``.
    """
    del query
    subject = extended_context.split(",")[0].strip() if extended_context.strip() else "the subject"
    lines = [
        f"#{index} How is {subject} described in {slice_.label}?"
        for index, slice_ in enumerate(slices, start=1)
    ]
    refs = ", ".join(f"#{index}" for index in range(1, len(slices) + 1))
    lines.append(f"#{len(slices) + 1} How does {subject} differ across {refs}?")
    steps: list[QDMRStep] = []
    for line in lines:
        match = _STEP.match(line)
        if match is None:
            raise ValueError(f"Comparative plan step is missing an index: {line}")
        index = int(match.group(1))
        body = match.group(2)
        steps.append(
            QDMRStep(
                step_index=index,
                operator="return",
                arguments=[body],
                references=reference_ids(body, exclude=index),
                instruction=line,
            )
        )
    return steps


def steps_are_valid(steps: list[QDMRStep], slice_count: int = 0) -> bool:
    """Accept a Break chain of sub-questions.

    A plan is valid when each step is numbered in order, every ``#k`` points
    at an earlier step, and at least one later step depends on an earlier one.
    There is no requirement for a retrieval step per slice.
    """
    del slice_count
    if len(steps) < 2:
        return False
    if [step.step_index for step in steps] != list(range(1, len(steps) + 1)):
        return False
    for step in steps:
        if not step.instruction.strip():
            return False
        if any(ref < 1 or ref >= step.step_index for ref in step.references):
            return False
    return any(step.references for step in steps)


_SYNTHESIZE = re.compile(
    r"\b(differ|difference|differences|compare|comparison|contrast|across|synthesize)\b",
    re.I,
)


def looks_like_synthesize(step: QDMRStep) -> bool:
    """True when the step is a contrast or synthesize question."""
    return bool(_SYNTHESIZE.search(step.instruction))


def ensure_synthesize_root(steps: list[QDMRStep]) -> list[QDMRStep]:
    """Make the last step the synthesize node that cites every earlier step.

    DSPy sometimes leaves a content step with no edge into the final node.
    The comparative plan needs one root that pulls the sub-questions together.
    """
    if len(steps) < 2:
        return steps
    last = steps[-1]
    if looks_like_synthesize(last):
        prior = list(range(1, last.step_index))
        if set(last.references) >= set(prior):
            return steps
        refs = ", ".join(f"#{index}" for index in prior)
        body = f"How do these accounts differ, given {refs}?"
        return list(steps[:-1]) + [
            QDMRStep(
                step_index=last.step_index,
                operator="return",
                arguments=[body],
                references=prior,
                instruction=f"#{last.step_index} {body}",
            )
        ]
    prior = list(range(1, len(steps) + 1))
    refs = ", ".join(f"#{index}" for index in prior)
    body = f"How do these accounts differ, given {refs}?"
    index = len(steps) + 1
    return list(steps) + [
        QDMRStep(
            step_index=index,
            operator="return",
            arguments=[body],
            references=prior,
            instruction=f"#{index} {body}",
        )
    ]
