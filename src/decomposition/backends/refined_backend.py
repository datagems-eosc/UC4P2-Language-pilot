"""Break checkpoint first, then a DSPy rewrite into benchmark sub-questions."""

from __future__ import annotations

from src.decomposition.backends.dspy_backend import DSPyQDMRRefiner
from src.decomposition.backends.finetuned_backend import FineTunedQDMRBackend
from src.decomposition.base import BaseQDMRDecomposer, QDMRStep
from src.decomposition.modes import FEW_SHOT, normalize_decompose_mode
from src.schemas.slice import ComparisonSlice


class RefinedQDMRBackend(BaseQDMRDecomposer):
    """Draft with the Break model, then ask a language model to rewrite it.

    The rewrite is kept only when it parses as a valid sub-question chain.
    Otherwise the Break draft is the decomposition.
    """

    def __init__(
        self,
        model_name_or_path: str = "",
        mock: bool = False,
        exclude_question_ids: set[str] | None = None,
        max_new_tokens: int = 96,
        decompose_mode: str = FEW_SHOT,
    ) -> None:
        self.decompose_mode = normalize_decompose_mode(decompose_mode)
        self._break = FineTunedQDMRBackend(
            model_name_or_path=model_name_or_path,
            mock=mock,
            max_new_tokens=max_new_tokens,
        )
        self._refiner = DSPyQDMRRefiner(
            exclude_question_ids,
            decompose_mode=self.decompose_mode,
        )
        self.last_draft = ""
        self.last_raw = ""
        self.last_error = ""
        self.used_fallback = False
        self.demo_questions = self._refiner.demo_questions

    @property
    def uses_mock(self) -> bool:
        return self._break.uses_mock

    def decompose(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
    ) -> list[QDMRStep]:
        draft_steps = self._break.decompose(query, slices, extended_context)
        self.last_draft = self._break.last_raw
        refined = self._refiner.refine(
            query,
            slices,
            extended_context,
            self.last_draft,
            draft_steps=draft_steps,
        )
        self.demo_questions = self._refiner.demo_questions
        if refined is None:
            self.used_fallback = True
            self.last_error = self._refiner.last_error
            self.last_raw = self.last_draft
            return draft_steps
        self.used_fallback = False
        self.last_error = ""
        self.last_raw = self._refiner.last_raw
        return refined
