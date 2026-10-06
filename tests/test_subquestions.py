from src.knowledge_extension.expander import expand_knowledge
from src.knowledge_extension.subquestions import generate_facet_lemma_subquestions
from src.schemas.slice import parse_query_intent

MARRIAGE = "How did a marriage look like in the 1800s compared to now?"


def test_facet_and_lemma_subquestions_cover_each_slice():
    intent, errors = parse_query_intent(MARRIAGE)
    assert not errors and intent is not None
    expansion = expand_knowledge(MARRIAGE, intent.target_concept, intent.slices)
    items = generate_facet_lemma_subquestions(
        MARRIAGE, intent.target_concept, intent.slices, expansion
    )
    assert intent.target_concept in expansion["thematic_facets"]
    questions = [item["question"] for item in items]
    assert any(intent.target_concept in question for question in questions)
    assert any("definition" in question for question in questions)
    slice_ids = {item["slice_id"] for item in items if item["slice_id"]}
    assert {slice_.slice_id for slice_ in intent.slices} <= slice_ids
    assert any(item["source"] == "contrast" for item in items)
