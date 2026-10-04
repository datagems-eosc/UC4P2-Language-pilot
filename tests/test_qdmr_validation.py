from src.decomposition.validation import validate_qdmr_graph

# Avoid bare "#1" confusion with step labels; use clear comparative Break text.
VALID = (
    "return marriages in the 1800s ;return legal status of those marriages "
    ";return marriages now ;return conceptual differences between #2 and #3"
)


def test_valid_break_graph_passes():
    ok, message = validate_qdmr_graph(VALID, expected_min_steps=4)
    assert ok is True
    assert message == ""


def test_forward_reference_is_rejected():
    ok, message = validate_qdmr_graph(
        "return #2 ;return marriages",
        expected_min_steps=2,
    )
    assert ok is False
    assert "forward" in message.lower() or "reference" in message.lower()


def test_missing_comparison_terminus_is_rejected():
    ok, message = validate_qdmr_graph(
        "return marriages in 1800s ;return marriages now",
        expected_min_steps=2,
    )
    assert ok is False
    assert "final" in message.lower() or "synthesize" in message.lower() or "compare" in message.lower()


def test_too_few_steps_is_rejected():
    ok, message = validate_qdmr_graph("return marriage", expected_min_steps=3)
    assert ok is False
    assert "at least" in message.lower() or "steps" in message.lower()
