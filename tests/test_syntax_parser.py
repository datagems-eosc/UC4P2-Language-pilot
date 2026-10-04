import pytest

from src.decomposition.base import QDMRStep, build_comparative_steps
from src.decomposition.graph_builder import build_graph, schedule
from src.decomposition.syntax_parser import (
    parse_decomposition,
    parse_operator,
    steps_to_break,
)
from src.schemas.slice import ComparisonSlice


def test_return_string_extracts_references_and_operator():
    steps = parse_decomposition("return X ;return #1 where Y")
    assert [step.operator for step in steps] == ["return", "return"]
    assert steps[0].references == []
    assert steps[0].instruction == "#1 X"
    assert steps[1].step_index == 2
    assert steps[1].references == [1]
    assert steps[1].arguments == ["#1 where Y"]


def test_lexicon_operators_and_bracket_arguments():
    text = "SELECT[marriage] ;FILTER[#1, published in the 1800s] ;COMPARATIVE[#1, #2]"
    steps = parse_decomposition(text)
    assert [step.operator for step in steps] == ["select", "filter", "comparative"]
    assert steps[1].arguments == ["#1", "published in the 1800s"]
    assert steps[1].references == [1]
    assert steps[2].references == [1, 2]
    operator, arguments = parse_operator("AGGREGATE[count, #2]")
    assert operator == "aggregate"
    assert arguments == ["count", "#2"]


def test_break_roundtrip_matches_comparative_plan():
    slices = [
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
    original = build_comparative_steps("How did marriage change?", slices, "husband")
    parsed = parse_decomposition(steps_to_break(original))
    assert [step.model_dump() for step in parsed] == [step.model_dump() for step in original]


def test_forward_reference_is_rejected():
    steps = [
        QDMRStep(step_index=1, operator="return", arguments=["#2"], references=[2], instruction="#1 #2"),
        QDMRStep(step_index=2, operator="return", arguments=["Y"], references=[], instruction="#2 Y"),
    ]
    with pytest.raises(ValueError, match="forward"):
        build_graph(steps)
    ready = schedule(
        [
            QDMRStep(step_index=1, operator="return", arguments=["X"], references=[], instruction="#1 X"),
            QDMRStep(step_index=2, operator="return", arguments=["Y"], references=[], instruction="#2 Y"),
            QDMRStep(
                step_index=3,
                operator="return",
                arguments=["#1 #2"],
                references=[1, 2],
                instruction="#3 #1 #2",
            ),
        ]
    )
    assert [[step.step_index for step in layer] for layer in ready] == [[1, 2], [3]]
