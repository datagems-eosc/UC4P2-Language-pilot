from src.evaluation.nlg import evaluate_against_ground_truth, nlg_metrics


def test_identical_strings_score_high():
    gold = "A city of Germany, the capital of Saxony."
    scores = nlg_metrics(gold, gold)
    assert scores["exact_match"] == 1.0
    assert scores["token_f1"] == 1.0
    assert scores["rouge1_f1"] == 1.0
    assert scores["bleu"] == 1.0
    assert scores["meteor"] == 1.0


def test_citation_marks_are_ignored():
    gold = "A city of Germany, the capital of Saxony."
    scores = nlg_metrics(f"{gold} [ref_1]", gold)
    assert scores["exact_match"] == 1.0


def test_unrelated_text_scores_low():
    scores = nlg_metrics("bananas and apples", "A city of Germany, the capital of Saxony.")
    assert scores["exact_match"] == 0.0
    assert scores["token_f1"] < 0.2


def test_benchmark_ground_truth_lookup_by_question():
    question = "How is Dresden defined?"
    gold = "A larger city in Germany, capital of Saxony."
    result = evaluate_against_ground_truth(question, gold, query_id="1")
    assert result["matched"] is True
    assert result["metrics"]["exact_match"] == 1.0
    assert "llm_judge" in result


def test_marriage_walkthrough_uses_benchmark_gold():
    result = evaluate_against_ground_truth(
        "How did a marriage look like in the 1800s compared to now?",
        "an answer",
        query_id="q-api",
        concept="marriage",
    )
    assert result["matched"] is True
    assert result["question_id"] == "9"
    assert result["gold_source"] == "pilot2_benchmark_english.v1.json"
    assert result["match"] == "concept_parent"
    assert "lifelong contract" in result["ground_truth"]


def test_defined_marriage_uses_the_child_gold_row():
    result = evaluate_against_ground_truth("How is marriage defined?", "placeholder")
    assert result["matched"] is True
    assert result["question_id"] == "10"


def test_missing_ground_truth_is_reported():
    result = evaluate_against_ground_truth(
        "How do Martian canals compare with Venusian clouds?",
        "an answer",
        query_id="q-api",
    )
    assert result["matched"] is False
    assert result["metrics"] == {}
