from src.knowledge_extension.expander import expand_knowledge, heuristic_expansion
from src.schemas.slice import parse_query_intent

MARRIAGE = "How did a marriage look like in the 1800s compared to now?"
US_SOURCES = (
    "Were descriptions of the US different in German sources "
    "compared to English sources in the 1900s?"
)
DRESDEN = (
    "How do historical descriptions of the Dresden's cultural nicknames "
    "and the reasons given for them vary across time?"
)


def test_offline_expansion_is_generic_not_question_specific():
    intent, errors = parse_query_intent(MARRIAGE)
    assert not errors and intent is not None
    expansion = heuristic_expansion(MARRIAGE, intent.target_concept, intent.slices)
    assert intent.target_concept in expansion["thematic_facets"]
    assert "definition" in expansion["thematic_facets"]
    assert "husband" not in expansion["thematic_facets"]
    assert "dowry" not in expansion["thematic_facets"]
    assert "coverture" not in expansion[intent.slices[0].slice_id]
    assert 2 <= len(expansion["feature_lenses"]) <= 4
    early = next(item for item in intent.slices if item.period_start < 1900)
    assert intent.target_concept in expansion[early.slice_id]


def test_same_schema_for_dresden_and_us_questions():
    for question in (DRESDEN, US_SOURCES):
        intent, errors = parse_query_intent(question)
        assert not errors and intent is not None
        expansion = expand_knowledge(question, intent.target_concept, intent.slices)
        assert intent.target_concept in expansion["thematic_facets"]
        assert "definition" in expansion["thematic_facets"]
        for slice_ in intent.slices:
            assert expansion[slice_.slice_id]
            assert intent.target_concept in expansion[slice_.slice_id]


def test_german_slice_does_not_invent_a_translation_lexicon():
    intent, errors = parse_query_intent(US_SOURCES)
    assert not errors and intent is not None
    expansion = expand_knowledge(US_SOURCES, intent.target_concept, intent.slices)
    german = next(item for item in intent.slices if item.language == "German")
    assert "Amerika" not in expansion[german.slice_id]
    assert any("German" in word for word in expansion[german.slice_id])
