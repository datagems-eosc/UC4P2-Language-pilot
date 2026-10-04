from pathlib import Path

import dspy

from src.decomposition.advanced_dspy_module import AdvancedQDMRDecomposer
from src.decomposition.optimizer import (
    compile_qdmr_engine,
    load_compiled_decomposer,
    qdmr_quality_metric,
)


def test_qdmr_quality_metric_rewards_valid_graphs():
    gold = dspy.Example(qdmr_string=(
        "return How is marriage described in 1800s? "
        ";return How is marriage described now? "
        ";return How do these accounts differ, given #1, #2?"
    ))
    pred = dspy.Prediction(qdmr_string=gold.qdmr_string)
    assert qdmr_quality_metric(gold, pred) >= 0.6
    assert qdmr_quality_metric(gold, dspy.Prediction(qdmr_string="return #2")) == 0.0


def test_compile_qdmr_engine_saves_and_reloads(tmp_path, monkeypatch):
    trainset = [
        dspy.Example(
            query="How did marriage change?",
            slices='["1800s", "present"]',
            thematic_facets='["marriage"]',
            qdmr_string=(
                "return How is marriage described in 1800s? "
                ";return How is marriage described in present? "
                ";return How do these accounts differ, given #1, #2?"
            ),
        ).with_inputs("query", "slices", "thematic_facets")
    ]
    student = AdvancedQDMRDecomposer()

    class FakeMIPRO:
        def __init__(self, *args, **kwargs):
            pass

        def compile(self, engine, **kwargs):
            return engine

    monkeypatch.setattr("dspy.teleprompt.MIPROv2", FakeMIPRO)

    output = tmp_path / "compiled_qdmr.json"
    compiled = compile_qdmr_engine(trainset, output_path=str(output), student=student)
    assert output.is_file()
    assert isinstance(compiled, AdvancedQDMRDecomposer)

    loaded = load_compiled_decomposer(str(output))
    assert isinstance(loaded, AdvancedQDMRDecomposer)
    assert Path(output).stat().st_size > 0
