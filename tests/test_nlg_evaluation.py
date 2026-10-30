from src.evaluation.nlg import (
    evaluate_against_ground_truth,
    list_data_questions,
    nlg_metrics,
)


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


def test_demo_catalog_lists_all_v2_questions():
    catalog = list_data_questions()
    assert catalog
    assert all(item["source"] == "pilot2_benchmark_english.v2.json" for item in catalog)
    ids = {item["query_id"] for item in catalog}
    assert ids == {str(i) for i in range(36)}
    parents = [item for item in catalog if item["parent"]]
    children = [item for item in catalog if not item["parent"]]
    assert {item["query_id"] for item in parents} == {
        "0",
        "4",
        "9",
        "15",
        "19",
        "23",
        "27",
        "31",
    }
    assert len(children) == 28
    assert all(item["parent_id"] for item in children)


def test_benchmark_ground_truth_lookup_by_question_id():
    result = evaluate_against_ground_truth(
        "How do historical descriptions of the Dresden's cultural nicknames "
        "and the reasons given for them vary across time?",
        "placeholder",
        query_id="0",
    )
    assert result["matched"] is True
    assert result["match"] == "question_id"
    assert result["question_id"] == "0"
    assert result["gold_source"] == "pilot2_benchmark_english.v2.json"
    assert "Athens" in result["ground_truth"] or "Florence" in result["ground_truth"]


def test_nested_subquestion_matches_exact_question_text():
    question = "How is Dresden described?"
    result = evaluate_against_ground_truth(question, "placeholder")
    assert result["matched"] is True
    assert result["match"] == "question"
    assert "capital" in result["ground_truth"].lower() or "Saxony" in result["ground_truth"]


def test_nested_subquestion_matches_by_subquestion_id():
    result = evaluate_against_ground_truth(
        "How is Dresden described?",
        "placeholder",
        query_id="1",
    )
    assert result["matched"] is True
    assert result["match"] == "question_id"
    assert result["question_id"] == "1"
    assert "capital" in result["ground_truth"].lower() or "Saxony" in result["ground_truth"]


def test_marriage_walkthrough_uses_exact_question_id():
    result = evaluate_against_ground_truth(
        "How does the definition of a valid marriage shift over time in the Western hemisphere?",
        "an answer",
        query_id="9",
    )
    assert result["matched"] is True
    assert result["question_id"] == "9"
    assert result["gold_source"] == "pilot2_benchmark_english.v2.json"
    assert result["match"] == "question_id"
    assert "marriage" in result["ground_truth"].lower()


def test_paraphrase_without_exact_id_does_not_match_neighbor_gold():
    result = evaluate_against_ground_truth(
        "How did a marriage look like in the 1800s compared to now?",
        "an answer",
        query_id="q-api",
        concept="marriage",
    )
    assert result["matched"] is False
    assert result["metrics"] == {}


def test_missing_ground_truth_is_reported():
    result = evaluate_against_ground_truth(
        "How do Martian canals compare with Venusian clouds?",
        "an answer",
        query_id="q-api",
    )
    assert result["matched"] is False
    assert result["metrics"] == {}
