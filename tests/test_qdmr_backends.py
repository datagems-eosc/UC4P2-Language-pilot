from src.decomposition.backends.dspy_backend import DSPyQDMRBackend
from src.decomposition.backends.finetuned_backend import FineTunedQDMRBackend
from src.decomposition.backends.refined_backend import RefinedQDMRBackend
from src.decomposition.base import QDMRStep
from src.decomposition.graph_builder import QDMRExecutionRunner, format_tree, schedule
from src.decomposition.modes import COT, FEW_SHOT, PREDICT
from src.schemas.slice import ComparisonSlice

SLICES = [
    ComparisonSlice(
        slice_id=f"slice_{index}",
        label=label,
        language="English",
        period_start=start,
        period_end=end,
    )
    for index, (label, start, end) in enumerate(
        (("1800s", 1800, 1899), ("1900s", 1900, 1999), ("present", 2026, 2026)),
        start=1,
    )
]


def test_both_backends_return_the_same_step_contract():
    query = "How did a marriage look like in the 1800s, the 1900s, and now?"
    dspy_steps = DSPyQDMRBackend().decompose(query, SLICES, "husband, wife")
    finetuned_steps = FineTunedQDMRBackend(mock=True).decompose(query, SLICES, "husband, wife")
    assert finetuned_steps[0].__class__ is QDMRStep
    assert [step.model_dump() for step in dspy_steps] == [
        step.model_dump() for step in finetuned_steps
    ]
    assert all("Retrieve" not in step.instruction for step in dspy_steps)
    assert dspy_steps[0].instruction.endswith("?")
    assert dspy_steps[-1].references == [1, 2, 3]
    layers = schedule(dspy_steps)
    assert [step.step_index for step in layers[0]] == [1, 2, 3]
    assert layers[1][0].references == [1, 2, 3]


def test_runner_dispatches_retrieval_before_synthesis():
    steps = DSPyQDMRBackend().decompose("compare marriage", SLICES, "")
    seen: list[int] = []

    def handler(step, results):
        assert set(step.references).issubset(results)
        seen.append(step.step_index)
        return step.instruction

    results = QDMRExecutionRunner(parallel=False).run(steps, handler)
    assert seen[:3] == [1, 2, 3]
    assert seen[-1] == len(steps)
    assert set(results) == {step.step_index for step in steps}


def test_refinement_keeps_the_break_draft_without_a_language_model():
    query = "How did a marriage look like in the 1800s, the 1900s, and now?"
    refined = RefinedQDMRBackend(mock=True)
    steps = refined.decompose(query, SLICES, "marriage")
    draft = FineTunedQDMRBackend(mock=True).decompose(query, SLICES, "marriage")
    assert refined.used_fallback is True
    assert refined.last_error == "no language model configured"
    assert [step.model_dump() for step in steps] == [step.model_dump() for step in draft]
    assert refined.last_draft.startswith("return ")


def test_asked_question_is_left_out_of_the_few_shots():
    from src.decomposition.benchmark_fewshots import iter_decompositions, refinement_examples

    items = {item["question_id"]: item for item in iter_decompositions()}
    asked = items["27"]["question"]
    demos = refinement_examples(
        exclude_question_ids={"0", "9", "27"},
        asked_question=asked,
        concept="Love",
        years=[1830, 2025],
        limit=2,
    )
    assert len(demos) == 2
    blobs = [
        " ".join([str(demo.query), str(demo.draft), str(demo.decomposition)])
        for demo in demos
    ]
    assert asked not in "\n".join(blobs)
    for question_id in ("0", "9", "27"):
        assert items[question_id]["question"] not in [str(demo.query) for demo in demos]

    refined = RefinedQDMRBackend(mock=True, exclude_question_ids={"0", "9", "27"})
    refined.decompose(asked, SLICES[:2], "Love")
    assert asked not in refined.demo_questions
    assert len(refined.demo_questions) <= 2
    assert all(items["27"]["question"] not in demo for demo in refined.demo_questions)


def test_graph_draws_an_arrow_for_each_cited_step():
    from src.decomposition.graph_view import render_graph

    steps = FineTunedQDMRBackend(mock=True).decompose("compare marriage", SLICES, "marriage")
    markup = render_graph(steps, "Break draft")
    assert "<svg" in markup
    assert "1800s" in markup
    assert markup.count("<path") >= 3


def test_comparison_places_ground_truth_beside_the_rewrite():
    from src.decomposition.graph_view import render_pair

    steps = FineTunedQDMRBackend(mock=True).decompose("compare marriage", SLICES, "marriage")
    markup = render_pair(steps, steps, "Ground truth", "Final sub-questions")
    assert markup.count("<svg") == 2
    assert "Ground truth" in markup and "Final sub-questions" in markup


def test_tree_puts_the_final_step_above_the_steps_it_cites():
    steps = FineTunedQDMRBackend(mock=True).decompose("compare marriage", SLICES, "marriage")
    text = format_tree(steps)
    assert text.startswith("#4 ")
    assert "├── #1 " in text
    assert "└── #3 " in text


def test_decompose_mode_selects_predict_cot_or_few_shot():
    predict = DSPyQDMRBackend(decompose_mode=PREDICT)
    predict._use_examples("How did marriage change?")
    assert predict.decompose_mode == PREDICT
    assert predict._predict.__class__.__name__ == "Predict"
    assert list(predict._predict.demos or []) == []

    few = DSPyQDMRBackend(decompose_mode=FEW_SHOT)
    few._use_examples("How did marriage change?")
    assert few.decompose_mode == FEW_SHOT
    assert few._predict.__class__.__name__ == "Predict"
    assert len(few._predict.demos) == 2

    cot = DSPyQDMRBackend(decompose_mode="ChainOfThought")
    cot._use_examples("How did marriage change?")
    assert cot.decompose_mode == COT
    assert cot._predict.__class__.__name__ == "ChainOfThought"
    assert list(cot._predict.demos or []) == []

    refined = RefinedQDMRBackend(mock=True, decompose_mode="cot")
    assert refined.decompose_mode == COT
    assert refined._refiner._predict.__class__.__name__ == "ChainOfThought"
