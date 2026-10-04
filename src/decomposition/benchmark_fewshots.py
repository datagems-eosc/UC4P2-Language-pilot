"""Few-shot QDMR exemplars taken from the Pilot 2 benchmark decompositions.

Each parent question lists subquestions. Those subquestions are the QDMR
steps. A final step asks how they differ and cites them as ``#k``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import dspy

from src.schemas.slice import ComparisonSlice

_BENCHMARK = Path(__file__).resolve().parents[2] / "data" / "pilot2_benchmark_english.v1.json"


def benchmark_path() -> Path:
    return _BENCHMARK.resolve()


def load_benchmark(path: Path | None = None) -> list[dict]:
    """Load the benchmark, inserting commas the source file sometimes omits."""
    text = (path or benchmark_path()).read_text(encoding="utf-8")
    text = re.sub(r"\}(\s*)\{", r"},\1{", text)
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("Benchmark JSON must be a list of questions.")
    return payload


def _years(parent: dict, by_id: dict[str, dict]) -> list[int]:
    years: list[int] = []
    for child_id in parent.get("Subquestion_IDs") or []:
        child = by_id.get(str(child_id)) or {}
        for source in child.get("source_metadata") or []:
            date = str(source.get("date") or "")
            if date.isdigit():
                year = int(date)
                if year not in years:
                    years.append(year)
    years.sort()
    return years


def _slices(years: list[int]) -> list[ComparisonSlice]:
    return [
        ComparisonSlice(
            slice_id=f"slice_{index}",
            label=str(year),
            language="English",
            period_start=year,
            period_end=year,
        )
        for index, year in enumerate(years, start=1)
    ]


def break_string(concept: str, years: list[int], subquestions: list[str]) -> str:
    """Turn benchmark subquestions into a Break string. No retrieval steps."""
    del concept, years
    parts: list[str] = []
    for question in subquestions:
        text = question.strip()
        if text and not text.endswith("?"):
            text = text.rstrip(".") + "?"
        parts.append(f"return {text}")
    refs = ", ".join(f"#{index}" for index in range(1, len(parts) + 1))
    parts.append(f"return How do these accounts differ, given {refs}?")
    return " ;".join(parts)


def iter_decompositions(records: list[dict] | None = None):
    """Yield parent questions that the benchmark already splits into subquestions."""
    records = records if records is not None else load_benchmark()
    by_id = {str(item["Question_ID"]): item for item in records}
    for parent in records:
        child_ids = parent.get("Subquestion_IDs") or []
        if len(child_ids) < 2:
            continue
        question = str(parent.get("Question") or "")
        if re.search(r"\b(weather|climate)\b", question, re.I):
            continue
        years = _years(parent, by_id)
        if len(years) < 2:
            continue
        subquestions = [
            str((by_id.get(str(child_id)) or {}).get("Question") or "").strip()
            for child_id in child_ids
        ]
        subquestions = [item for item in subquestions if item]
        concept = str(parent.get("Concept") or "").strip()
        yield {
            "question_id": str(parent["Question_ID"]),
            "question": question,
            "concept": concept,
            "years": years,
            "subquestions": subquestions,
            "slices": _slices(years),
            "decomposition": break_string(concept, years, subquestions),
        }


def synthetic_break_draft(concept: str, years: list[int]) -> str:
    """Telegraphic Break-style draft, the shape the checkpoint usually emits."""
    subject = concept.strip() or "the subject"
    parts = [f"return {subject}"]
    for year in years:
        parts.append(f"return #1 in {year}")
    cited = ", ".join(f"#{index}" for index in range(2, len(years) + 2))
    parts.append(f"return conceptual differences between {cited}")
    return " ;".join(parts)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def example_includes_question(item: dict, asked_question: str) -> bool:
    """True when this example is, or contains, the question being decomposed."""
    asked = _norm(asked_question)
    if not asked:
        return False
    fields = [_norm(item["question"]), *(_norm(part) for part in item["subquestions"])]
    fields.append(_norm(item["decomposition"]))
    if asked in fields:
        return True
    return len(asked) >= 40 and any(asked in field for field in fields)


def _selected_items(
    exclude_question_ids: set[str] | None = None,
    asked_question: str = "",
) -> list[dict]:
    """Example pool with the question under test left out."""
    excluded = {str(question_id) for question_id in (exclude_question_ids or set())}
    selected: list[dict] = []
    for item in iter_decompositions():
        if item["question_id"] in excluded:
            continue
        if example_includes_question(item, asked_question):
            continue
        selected.append(item)
    return selected


def fewshot_examples(
    exclude_question_ids: set[str] | None = None,
    asked_question: str = "",
) -> list[dspy.Example]:
    """DSPy demos. The asked question is never one of the examples."""
    examples: list[dspy.Example] = []
    for item in _selected_items(exclude_question_ids, asked_question):
        examples.append(
            dspy.Example(
                query=item["question"],
                slices=json.dumps([slice_.model_dump() for slice_ in item["slices"]]),
                extended_context=item["concept"],
                decomposition=item["decomposition"],
            ).with_inputs("query", "slices", "extended_context")
        )
    return examples


def refinement_examples(
    exclude_question_ids: set[str] | None = None,
    asked_question: str = "",
    concept: str = "",
    years: list[int] | None = None,
    limit: int = 2,
) -> list[dspy.Example]:
    """Nearest demos that rewrite a telegraphic Break draft into sub-questions."""
    from src.decomposition.refine_utils import nearest_items

    items = nearest_items(
        _selected_items(exclude_question_ids, asked_question),
        asked_question=asked_question,
        concept=concept,
        years=list(years or []),
        limit=limit,
    )
    examples: list[dspy.Example] = []
    for item in items:
        examples.append(
            dspy.Example(
                query=item["question"],
                draft=synthetic_break_draft(item["concept"], item["years"]),
                extended_context=item["concept"],
                decomposition=item["decomposition"],
            ).with_inputs("query", "draft", "extended_context")
        )
    return examples


def advanced_plan_examples(
    exclude_question_ids: set[str] | None = None,
    asked_question: str = "",
    concept: str = "",
    years: list[int] | None = None,
    limit: int = 2,
) -> list[dspy.Example]:
    """Nearest demos for Advanced stage 1: Break draft → readable sub-questions."""
    from src.decomposition.refine_utils import nearest_items

    items = nearest_items(
        _selected_items(exclude_question_ids, asked_question),
        asked_question=asked_question,
        concept=concept,
        years=list(years or []),
        limit=limit,
    )
    examples: list[dspy.Example] = []
    for item in items:
        labels = [slice_.label for slice_ in item["slices"]]
        examples.append(
            dspy.Example(
                query=item["question"],
                slices=json.dumps(labels),
                thematic_facets=json.dumps([item["concept"]]),
                draft=synthetic_break_draft(item["concept"], item["years"]),
                slice_extraction_goals=json.dumps(item["subquestions"]),
            ).with_inputs("query", "slices", "thematic_facets", "draft")
        )
    return examples


def advanced_dag_examples(
    exclude_question_ids: set[str] | None = None,
    asked_question: str = "",
    concept: str = "",
    years: list[int] | None = None,
    limit: int = 2,
) -> list[dspy.Example]:
    """Nearest demos for Advanced stage 2: goals → Break string with synthesize."""
    from src.decomposition.refine_utils import nearest_items

    items = nearest_items(
        _selected_items(exclude_question_ids, asked_question),
        asked_question=asked_question,
        concept=concept,
        years=list(years or []),
        limit=limit,
    )
    examples: list[dspy.Example] = []
    for item in items:
        examples.append(
            dspy.Example(
                query=item["question"],
                slice_goals=json.dumps(item["subquestions"]),
                draft=synthetic_break_draft(item["concept"], item["years"]),
                qdmr_string=item["decomposition"],
            ).with_inputs("query", "slice_goals", "draft")
        )
    return examples
