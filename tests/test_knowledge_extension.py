from src.knowledge_extension.expander import expand_knowledge
from src.schemas.slice import parse_query_intent

MARRIAGE = "How did a marriage look like in the 1800s compared to now?"
US_SOURCES = (
    "Were descriptions of the US different in German sources "
    "compared to English sources in the 1900s?"
)


def test_marriage_facet_expansion_and_lenses():
    intent, errors = parse_query_intent(MARRIAGE)
    assert not errors and intent is not None
    expansion = expand_knowledge(MARRIAGE, intent.target_concept, intent.slices)
    for facet in ("husband", "wife", "divorce", "dowry", "property ownership", "spousal duties"):
        assert facet in expansion["thematic_facets"]
    assert expansion["feature_lenses"] == [
        "legal_standing",
        "economic_contract",
        "social_stance",
    ]
    early = next(item for item in intent.slices if item.period_start < 1900)
    assert expansion[early.slice_id] == ["coverture", "matrimony", "common-law"]


def test_us_perceptions_include_period_and_language_variants():
    intent, errors = parse_query_intent(US_SOURCES)
    assert not errors and intent is not None
    expansion = expand_knowledge(US_SOURCES, intent.target_concept, intent.slices)
    german = next(item for item in intent.slices if item.language == "German")
    for token in ("Amerika", "Vereinigte Staaten", "Nordamerika"):
        assert token in expansion[german.slice_id]
    assert 2 <= len(expansion["feature_lenses"]) <= 4
    assert "social_stance" in expansion["feature_lenses"]
