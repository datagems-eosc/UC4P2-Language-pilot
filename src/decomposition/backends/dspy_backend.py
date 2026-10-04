"""DSPy few-shot backend. No local checkpoint is required."""

from __future__ import annotations

import dspy

from src.decomposition.base import (
    BaseQDMRDecomposer,
    QDMRStep,
    build_comparative_steps,
    ensure_synthesize_root,
    steps_are_valid,
)
from src.decomposition.benchmark_fewshots import fewshot_examples, refinement_examples
from src.decomposition.modes import COT, FEW_SHOT, normalize_decompose_mode
from src.decomposition.refine_utils import transfer_break_structure
from src.decomposition.syntax_parser import parse_decomposition, steps_to_break
from src.schemas.slice import ComparisonSlice


def _dspy_module(signature: type[dspy.Signature], mode: str):
    """Predict, ChainOfThought, or few-shot Predict — the notebook's three styles."""
    if mode == COT:
        return dspy.ChainOfThought(signature)
    return dspy.Predict(signature)


class QDMRSignature(dspy.Signature):
    """Decompose a comparative question into Break QDMR steps."""

    query: str = dspy.InputField()
    slices: str = dspy.InputField(desc="JSON list of comparison slices")
    extended_context: str = dspy.InputField(desc="Facets and per-slice lemmas")
    decomposition: str = dspy.OutputField(
        desc="Semicolon-delimited sub-questions, as in 'return How is X defined? "
        ";return What terms are used for X? ;return How do these accounts differ, given #1, #2?'. "
        "Do not emit a retrieval step per slice. Cite earlier sub-questions as #k."
    )


class DSPyQDMRBackend(BaseQDMRDecomposer):
    """Prompt a configured language model, then parse the Break string.

    Demonstrations are the benchmark's own subquestion decompositions.
    Pass ``exclude_question_ids`` to hold a question out of the prompt.
    """

    def __init__(
        self,
        exclude_question_ids: set[str] | None = None,
        decompose_mode: str = FEW_SHOT,
    ) -> None:
        self.exclude_question_ids = set(exclude_question_ids or ())
        self.decompose_mode = normalize_decompose_mode(decompose_mode)
        self.last_raw = ""
        self.last_error = ""
        self.used_fallback = False
        self._predict = _dspy_module(QDMRSignature, self.decompose_mode)
        self.demo_questions: list[str] = []

    def _use_examples(self, query: str) -> None:
        if self.decompose_mode != FEW_SHOT:
            self._predict.demos = []
            self.demo_questions = []
            return
        demos = fewshot_examples(self.exclude_question_ids, asked_question=query)
        self._predict.demos = demos[:2]
        self.demo_questions = [str(demo.query) for demo in self._predict.demos]

    def decompose(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
    ) -> list[QDMRStep]:
        fallback = build_comparative_steps(query, slices, extended_context)
        self.last_raw = ""
        self.last_error = ""
        self._use_examples(query)
        if getattr(dspy.settings, "lm", None) is None:
            self.used_fallback = True
            self.last_error = "no language model configured"
            return fallback
        try:
            import json

            prediction = self._predict(
                query=query,
                slices=json.dumps([slice_.model_dump() for slice_ in slices]),
                extended_context=extended_context,
            )
        except Exception as exc:
            self.used_fallback = True
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            return fallback
        raw = str(getattr(prediction, "decomposition", "") or "").strip()
        self.last_raw = raw
        if not raw:
            self.used_fallback = True
            return fallback
        try:
            parsed = parse_decomposition(raw)
        except Exception:
            self.used_fallback = True
            return fallback
        parsed = ensure_synthesize_root(parsed)
        if steps_are_valid(parsed, len(slices)):
            self.used_fallback = False
            return parsed
        self.used_fallback = True
        return fallback


class RefineQDMRSignature(dspy.Signature):
    """Rewrite only the wording of a Break draft.

    The draft's #k connections are the plan. Keep the same number of steps
    and the same citations. If step #3 says 'given #1', the rewrite of #3
    must still depend on #1. Only expand telegraphic phrases into full
    sub-questions ending with '?'. The last step is the synthesize node and
    cites every earlier step. Do not invent a flat list of independent
    questions. Do not add retrieval steps.
    """

    query: str = dspy.InputField()
    draft: str = dspy.InputField(
        desc="Break decomposition. Keep every #k edge from this draft."
    )
    extended_context: str = dspy.InputField(desc="Subject of the comparison")
    decomposition: str = dspy.OutputField(
        desc="Same Break skeleton and #k citations, with fuller sub-question "
        "wording, ending in 'return How do these accounts differ, given #1, #2, ...?'."
    )


class DSPyQDMRRefiner:
    """Rewrite Break wording; keep the Break dependency graph."""

    def __init__(
        self,
        exclude_question_ids: set[str] | None = None,
        max_demos: int = 2,
        decompose_mode: str = FEW_SHOT,
    ) -> None:
        self.exclude_question_ids = set(exclude_question_ids or ())
        self.max_demos = max_demos
        self.decompose_mode = normalize_decompose_mode(decompose_mode)
        self.last_raw = ""
        self.last_error = ""
        self.last_score: dict | None = None
        self._predict = _dspy_module(RefineQDMRSignature, self.decompose_mode)
        self.demo_questions: list[str] = []

    def _use_examples(
        self,
        query: str,
        *,
        concept: str = "",
        years: list[int] | None = None,
    ) -> None:
        if self.decompose_mode != FEW_SHOT:
            self._predict.demos = []
            self.demo_questions = []
            return
        demos = refinement_examples(
            self.exclude_question_ids,
            asked_question=query,
            concept=concept,
            years=years,
            limit=self.max_demos,
        )
        self._predict.demos = demos
        self.demo_questions = [str(demo.query) for demo in demos]

    def refine(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str,
        draft: str,
        draft_steps: list[QDMRStep] | None = None,
    ) -> list[QDMRStep] | None:
        """Return rewritten steps, or None when the draft should be kept."""
        self.last_raw = ""
        self.last_error = ""
        self.last_score = None
        years = [
            int(slice_.label)
            for slice_ in slices
            if str(slice_.label).isdigit()
        ]
        self._use_examples(query, concept=extended_context, years=years)
        if getattr(dspy.settings, "lm", None) is None:
            self.last_error = "no language model configured"
            return None
        try:
            prediction = self._predict(
                query=query,
                draft=draft,
                extended_context=extended_context,
            )
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            return None
        raw = str(getattr(prediction, "decomposition", "") or "").strip()
        self.last_raw = raw
        if not raw:
            self.last_error = "empty refinement"
            return None
        try:
            parsed = parse_decomposition(raw)
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {exc}"
            return None
        if draft_steps:
            parsed = transfer_break_structure(draft_steps, parsed)
        else:
            parsed = ensure_synthesize_root(parsed)
        self.last_raw = steps_to_break(parsed) if parsed else raw
        if steps_are_valid(parsed, len(slices)):
            return parsed
        self.last_error = "refinement did not parse as sub-questions"
        return None
