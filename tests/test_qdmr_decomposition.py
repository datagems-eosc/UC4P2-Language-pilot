from src.decomposition.base import steps_are_valid
from src.decomposition.qdmr_generator import decompose_question
from src.decomposition.syntax_parser import parse_decomposition
from src.schemas.slice import ComparisonSlice, parse_query_intent


def test_three_slices_produce_retrieval_steps_and_dependency_refs():
    slices = [
        ComparisonSlice(
            slice_id=f"slice_{index}",
            label=label,
            language="English",
            period_start=start,
            period_end=end,
            corpus_id="corpus",
        )
        for index, (label, start, end) in enumerate(
            (("1800s", 1800, 1899), ("1900s", 1900, 1999), ("present", 2026, 2026)),
            start=1,
        )
    ]
    tasks = decompose_question("How did marriage change?", slices, "marriage")
    assert all("Retrieve" not in task for task in tasks)
    assert tasks[0].startswith("#1 How is marriage described in 1800s?")
    assert tasks[1].startswith("#2 How is marriage described in 1900s?")
    assert tasks[2].startswith("#3 How is marriage described in present?")
    contrast = tasks[-1]
    for reference in ("#1", "#2", "#3"):
        assert reference in contrast
    assert contrast.startswith("#4 ")


def test_parsed_three_period_question_decomposes():
    query = "How did a marriage look like in the 1800s, the 1900s, and now?"
    intent, errors = parse_query_intent(query)
    assert not errors and intent is not None
    assert len(intent.slices) == 3
    tasks = decompose_question(query, intent.slices, "marriage")
    assert all("Retrieve" not in task for task in tasks)
    assert tasks[-1].startswith("#4 ")
    assert "#1" in tasks[-1] and "#2" in tasks[-1] and "#3" in tasks[-1]


def test_break_subquestions_are_accepted_without_retrieve_steps():
    model_output = (
        "return love ;return #1 in the early 19th century "
        ";return #1 today ;return conceptual differences between #2 and #3"
    )
    benchmark_style = (
        "return How is love defined? "
        ";return Which qualities are necessary for love to develop? "
        ";return How do these accounts differ, given #1, #2?"
    )
    for text in (model_output, benchmark_style):
        steps = parse_decomposition(text)
        assert steps_are_valid(steps)
        assert all("Retrieve" not in step.instruction for step in steps)


def test_synthesize_root_connects_every_earlier_step():
    from src.decomposition.base import ensure_synthesize_root

    disconnected = parse_decomposition(
        "return How is love defined? "
        ";return Which qualities are necessary for love to develop? "
        ";return What problems are associated with love? "
        ";return How do these accounts differ, given #1, #2?"
    )
    fixed = ensure_synthesize_root(disconnected)
    assert fixed[-1].references == [1, 2, 3]
    assert "given #1, #2, #3" in fixed[-1].instruction
    assert len(fixed) == 4

    content_only = parse_decomposition(
        "return How is marriage defined? ;return What is the legal age to marry?"
    )
    with_root = ensure_synthesize_root(content_only)
    assert len(with_root) == 3
    assert with_root[-1].references == [1, 2]


def test_break_marriage_draft_is_expanded_into_readable_questions():
    from src.decomposition.refine_utils import (
        format_edges,
        normalize_break_steps,
        score_against_gold,
        transfer_break_structure,
    )
    from src.schemas.slice import ComparisonSlice

    slices = [
        ComparisonSlice(
            slice_id="slice_1",
            label="1830",
            language="English",
            period_start=1830,
            period_end=1830,
        ),
        ComparisonSlice(
            slice_id="slice_2",
            label="2025",
            language="English",
            period_start=2025,
            period_end=2025,
        ),
    ]
    strange = parse_decomposition(
        "return marriage ;return #1 in 1830 ;return #1 today "
        ";return conceptual differences between #2 and #3"
    )
    polished = normalize_break_steps(strange, concept="Marriage", slices=slices)
    assert all("?" in step.instruction for step in polished)
    assert "How is Marriage defined?" in polished[0].instruction
    assert polished[-1].references == [1, 2, 3]
    gold = parse_decomposition(
        "return How is marriage defined? "
        ";return What is the legal age to marry? "
        ";return How do these accounts differ, given #1, #2?"
    )
    metric = score_against_gold(gold, polished)
    assert metric["valid"] is True
    assert metric["synthesize"] is True
    assert metric["score"] > 0

    flat_dspy = parse_decomposition(
        "return How is marriage defined? "
        ";return What is the legal age to marry? "
        ";return Which requirements are needed? "
        ";return How do these accounts differ, given #1, #2, #3?"
    )
    merged = transfer_break_structure(polished, flat_dspy)
    assert [step.references for step in merged[:-1]] == [
        step.references for step in polished[:-1]
    ]
    assert "←" in format_edges(merged)
