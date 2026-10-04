from types import SimpleNamespace

import pytest

from src.decomposition.advanced_dspy_module import (
    AdvancedQDMRDecomposer,
    AssertionFailure,
)
from src.schemas.slice import ComparisonSlice

SLICES = [
    ComparisonSlice(
        slice_id="slice_1",
        label="1800s",
        language="English",
        period_start=1800,
        period_end=1899,
    ),
    ComparisonSlice(
        slice_id="slice_2",
        label="present",
        language="English",
        period_start=2026,
        period_end=2026,
    ),
]

BAD = "return #2 ;return marriages"
GOOD = (
    "return How is marriage described in 1800s? "
    ";return How is marriage described in present? "
    ";return How do these accounts differ, given #1, #2?"
)


def test_assertion_backtracks_from_malformed_to_valid_qdmr():
    module = AdvancedQDMRDecomposer(max_assertion_retries=3)
    module.program.slice_planner = lambda **kwargs: SimpleNamespace(
        slice_extraction_goals='["goal 1800s", "goal present"]'
    )
    module.program.dag_compiler = lambda **kwargs: SimpleNamespace(qdmr_string=BAD)
    module.program.dag_repair = lambda **kwargs: SimpleNamespace(qdmr_string=GOOD)

    draft = (
        "return marriage in 1800s ;return marriage now "
        ";return difference of #1 and #2"
    )
    prediction = module.forward(
        query="How did marriage change?",
        slices=["1800s", "present"],
        thematic_facets=["marriage"],
        draft=draft,
    )
    assert prediction.qdmr_string == GOOD
    assert module.assertion_repairs >= 1

    steps = module.decompose(
        "How did marriage change?", SLICES, "marriage", draft=draft
    )
    assert len(steps) >= 3
    assert steps[-1].references == [1, 2]


def test_exhausted_assertions_raise_and_decompose_falls_back():
    module = AdvancedQDMRDecomposer(max_assertion_retries=2)
    module.program.slice_planner = lambda **kwargs: SimpleNamespace(
        slice_extraction_goals='["a", "b"]'
    )
    module.program.dag_compiler = lambda **kwargs: SimpleNamespace(qdmr_string=BAD)
    module.program.dag_repair = lambda **kwargs: SimpleNamespace(qdmr_string=BAD)

    with pytest.raises(AssertionFailure):
        module.forward(query="q", slices=["1800s", "present"], thematic_facets=[])

    steps = module.decompose("How did marriage change?", SLICES, "marriage")
    assert steps[-1].references
    assert module.last_error
