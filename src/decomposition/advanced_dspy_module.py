"""Multi-stage DSPy QDMR decomposer with assert-style backtrack and retry.

DSPy 3.x no longer ships ``dspy.Assert``. This module keeps the same contract:
validate the DAG string, then re-invoke the graph synthesizer with the error
feedback until the structure is valid or retries are exhausted.

The Break draft is the structural input: stage 1 expands its telegraphic
phrases into readable sub-questions; stage 2 rebuilds the Break string while
keeping the draft's ``#k`` edges; ``transfer_break_structure`` enforces that
skeleton after parsing.
"""

from __future__ import annotations

import json
from typing import Any

import dspy

from src.decomposition.base import (
    BaseQDMRDecomposer,
    QDMRStep,
    build_comparative_steps,
    ensure_synthesize_root,
    steps_are_valid,
)
from src.decomposition.benchmark_fewshots import (
    advanced_dag_examples,
    advanced_plan_examples,
)
from src.decomposition.refine_utils import transfer_break_structure
from src.decomposition.syntax_parser import parse_decomposition, steps_to_break
from src.decomposition.validation import validate_qdmr_graph
from src.schemas.slice import ComparisonSlice


class AnalyzeSlicesAndEntities(dspy.Signature):
    """Expand the Break draft into one readable sub-question per slice.

    The Break ``draft`` is the plan. Expand each telegraphic content step into
    a full natural-language question ending with '?'. Keep the same number of
    content steps as the draft (excluding the final synthesize). Stay faithful
    to the parent query and subject. Do not invent extra places or entities.
    Do not emit Break ``return`` / ``#k`` syntax in the goals list.
    """

    query: str = dspy.InputField(desc="Comparative historical question")
    slices: str = dspy.InputField(desc="JSON list of year / period labels")
    thematic_facets: str = dspy.InputField(
        desc="JSON list; first item is the subject being compared"
    )
    draft: str = dspy.InputField(
        desc="Break model draft. Expand its content steps into full questions."
    )
    slice_extraction_goals: str = dspy.OutputField(
        desc="JSON list of full sub-questions, one per Break content step, each ending with '?'"
    )


class SynthesizeQDMRDAG(dspy.Signature):
    """Compile expanded goals back onto the Break draft skeleton.

    Emit semicolon-delimited 'return <question>?' steps. Keep the draft's
    step count and every #k edge. Wording comes from slice_goals. The final
    step must be 'return How do these accounts differ, given #1, #2, ...?'.
    """

    query: str = dspy.InputField()
    slice_goals: str = dspy.InputField(desc="JSON list of full sub-questions")
    draft: str = dspy.InputField(
        desc="Break skeleton. Keep its step count and #k edges."
    )
    qdmr_string: str = dspy.OutputField(
        desc="Semicolon-delimited return steps ending in a synthesize step"
    )


class RepairQDMRDAG(dspy.Signature):
    """Repair a malformed Break QDMR string using a validator error message."""

    query: str = dspy.InputField()
    slice_goals: str = dspy.InputField()
    draft: str = dspy.InputField(desc="Break skeleton to preserve")
    broken_qdmr: str = dspy.InputField(desc="Previous invalid QDMR string")
    error_message: str = dspy.InputField(desc="Validator failure to fix")
    qdmr_string: str = dspy.OutputField(
        desc="Corrected semicolon-delimited Break QDMR with full sub-questions"
    )


class AssertionFailure(RuntimeError):
    """Raised when a QDMR assertion fails and retries are exhausted."""

    def __init__(self, message: str, *, target_module: str | None = None):
        super().__init__(message)
        self.target_module = target_module


def assert_qdmr(
    condition: bool,
    message: str,
    *,
    target_module: str | None = None,
) -> None:
    """DSPy-Assert equivalent for DSPy 3.x (native Assert was removed)."""
    if not condition:
        raise AssertionFailure(message, target_module=target_module)


def _parse_goal_list(raw: str, fallback: list[str]) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        payload = json.loads(text)
        if isinstance(payload, list):
            goals = [str(item).strip() for item in payload if str(item).strip()]
            return goals or fallback
    except json.JSONDecodeError:
        pass
    parts = [part.strip(" -\t") for part in text.replace(";", "\n").splitlines()]
    goals = [part for part in parts if part]
    return goals or fallback


def _as_question(text: str) -> str:
    body = text.strip()
    if body.lower().startswith("return "):
        body = body[7:].strip()
    if body and not body.endswith("?"):
        body = body.rstrip(".") + "?"
    return body


class AdvancedQDMRProgram(dspy.Module):
    """Two-stage QDMR planner with structural assertions and repair retries."""

    def __init__(self, max_assertion_retries: int = 3) -> None:
        super().__init__()
        self.max_assertion_retries = max_assertion_retries
        self.slice_planner = dspy.ChainOfThought(AnalyzeSlicesAndEntities)
        self.dag_compiler = dspy.ChainOfThought(SynthesizeQDMRDAG)
        self.dag_repair = dspy.ChainOfThought(RepairQDMRDAG)
        self.last_raw = ""
        self.last_error = ""
        self.last_goals: list[str] = []
        self.assertion_repairs = 0
        self.demo_questions: list[str] = []

    def forward(
        self,
        query: str,
        slices: list[str],
        thematic_facets: list[str] | None = None,
        draft: str = "",
    ) -> dspy.Prediction:
        facets = thematic_facets or []
        subject = facets[0] if facets else "the subject"
        draft_text = (draft or "").strip()
        fallback_goals = [
            f"How is {subject} described in {label}?" for label in slices
        ]
        plan = self.slice_planner(
            query=query,
            slices=json.dumps(slices),
            thematic_facets=json.dumps(facets),
            draft=draft_text,
        )
        goals = [
            _as_question(goal)
            for goal in _parse_goal_list(
                str(getattr(plan, "slice_extraction_goals", "")), fallback_goals
            )
        ]
        self.last_goals = goals
        goals_json = json.dumps(goals)
        dag = self.dag_compiler(
            query=query, slice_goals=goals_json, draft=draft_text
        )
        qdmr = str(getattr(dag, "qdmr_string", "") or "").strip()
        expected = max(len(slices) + 1, 2)
        self.assertion_repairs = 0

        for attempt in range(self.max_assertion_retries):
            valid, message = validate_qdmr_graph(qdmr, expected_min_steps=expected)
            if valid:
                self.last_raw = qdmr
                self.last_error = ""
                return dspy.Prediction(
                    slice_extraction_goals=goals,
                    qdmr_string=qdmr,
                )
            self.assertion_repairs += 1
            if attempt + 1 >= self.max_assertion_retries:
                break
            repair = self.dag_repair(
                query=query,
                slice_goals=goals_json,
                draft=draft_text,
                broken_qdmr=qdmr,
                error_message=(
                    f"Your QDMR decomposition violates syntax constraints: {message}. "
                    "Rewrite it as full sub-questions ending with '?', with every #k "
                    "pointing strictly backward, and a final "
                    "'How do these accounts differ, given #1, #2, ...?' step."
                ),
            )
            qdmr = str(getattr(repair, "qdmr_string", "") or "").strip()

        valid, message = validate_qdmr_graph(qdmr, expected_min_steps=expected)
        if valid:
            self.last_raw = qdmr
            self.last_error = ""
            return dspy.Prediction(slice_extraction_goals=goals, qdmr_string=qdmr)
        assert_qdmr(
            False,
            f"Your QDMR decomposition violates syntax constraints: {message}. "
            "Rewrite it ensuring all #k references point strictly backward "
            "and the final step compares previous steps.",
            target_module="dag_compiler",
        )
        raise AssertionError("unreachable")


class AdvancedQDMRDecomposer(BaseQDMRDecomposer):
    """Pipeline adapter around ``AdvancedQDMRProgram`` (avoids ABC/metaclass clash)."""

    def __init__(
        self,
        max_assertion_retries: int = 3,
        exclude_question_ids: set[str] | None = None,
        max_demos: int = 2,
    ) -> None:
        self.program = AdvancedQDMRProgram(max_assertion_retries=max_assertion_retries)
        self.exclude_question_ids = set(exclude_question_ids or ())
        self.max_demos = max_demos

    @property
    def last_raw(self) -> str:
        return self.program.last_raw

    @property
    def last_error(self) -> str:
        return self.program.last_error

    @property
    def assertion_repairs(self) -> int:
        return self.program.assertion_repairs

    @property
    def demo_questions(self) -> list[str]:
        return self.program.demo_questions

    def forward(self, **kwargs: Any) -> dspy.Prediction:
        return self.program(**kwargs)

    def save(self, path: str) -> None:
        self.program.save(path)

    def load(self, path: str) -> None:
        self.program.load(path)

    def _use_examples(
        self,
        query: str,
        *,
        concept: str = "",
        years: list[int] | None = None,
    ) -> None:
        plan_demos = advanced_plan_examples(
            self.exclude_question_ids,
            asked_question=query,
            concept=concept,
            years=years,
            limit=self.max_demos,
        )
        dag_demos = advanced_dag_examples(
            self.exclude_question_ids,
            asked_question=query,
            concept=concept,
            years=years,
            limit=self.max_demos,
        )
        self.program.slice_planner.demos = plan_demos
        self.program.dag_compiler.demos = dag_demos
        self.program.dag_repair.demos = dag_demos
        self.program.demo_questions = [str(demo.query) for demo in plan_demos]

    def decompose(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
        draft: str = "",
        draft_steps: list[QDMRStep] | None = None,
    ) -> list[QDMRStep]:
        """Expand a Break draft with multi-stage DSPy; keep Break ``#k`` edges.

        ``draft`` / ``draft_steps`` should come from the Break (finetuned)
        backend. When both are missing, falls back to a comparative stub plan.
        """
        labels = [slice_.label for slice_ in slices]
        facets = [
            part.strip() for part in extended_context.split(",") if part.strip()
        ] or ([extended_context.strip()] if extended_context.strip() else [])
        years = [int(label) for label in labels if str(label).isdigit()]
        fallback = build_comparative_steps(query, slices, extended_context)
        if draft_steps and not draft:
            draft = steps_to_break(draft_steps)
        if not draft.strip() and not draft_steps:
            self.program.last_error = "Break draft required for advanced DSPy"
            return fallback
        self._use_examples(query, concept=extended_context, years=years)
        try:
            prediction = self.forward(
                query=query,
                slices=labels,
                thematic_facets=facets,
                draft=draft,
            )
            qdmr = str(getattr(prediction, "qdmr_string", "") or "").strip()
            self.program.last_raw = qdmr
            parsed = parse_decomposition(qdmr)
            if draft_steps:
                parsed = transfer_break_structure(draft_steps, parsed)
            else:
                parsed = ensure_synthesize_root(parsed)
            self.program.last_raw = steps_to_break(parsed) if parsed else qdmr
            if steps_are_valid(parsed, len(slices)):
                return parsed
            self.program.last_error = "advanced output failed structural checks"
            return draft_steps or fallback
        except AssertionFailure as exc:
            self.program.last_error = str(exc)
            return draft_steps or fallback
        except Exception as exc:
            self.program.last_error = f"{exc.__class__.__name__}: {exc}"
            return draft_steps or fallback


def load_compiled_state(module: AdvancedQDMRDecomposer, path: str) -> AdvancedQDMRDecomposer:
    """Load MIPROv2 / ``Module.save`` weights into an advanced decomposer."""
    module.load(path)
    return module
