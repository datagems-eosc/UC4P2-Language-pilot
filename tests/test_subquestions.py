from src.knowledge_extension.expander import expand_knowledge
from src.knowledge_extension.subquestions import (
    generate_facet_lemma_subquestions,
    qdmr_from_extension_questions,
    retrieval_jobs_from_extension,
)
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
    plan = qdmr_from_extension_questions(items, concept=intent.target_concept)
    assert plan[0].startswith("#1 ")
    assert "differ across" in plan[-1]
    assert any("definition" in step.lower() for step in plan)
    jobs = retrieval_jobs_from_extension(
        items,
        intent.slices,
        {slice_.slice_id: expansion.get(slice_.slice_id) or [] for slice_ in intent.slices},
    )
    assert {job["slice"].slice_id for job in jobs} == {slice_.slice_id for slice_ in intent.slices}
    assert all(job["query"] == job["question"] for job in jobs)
    assert len(jobs) >= len(intent.slices)
