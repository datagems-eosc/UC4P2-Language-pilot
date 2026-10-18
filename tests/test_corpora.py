from src.decomposition.benchmark_fewshots import load_benchmark
from src.retrieval.corpora import (
    LANGUAGE_DATASETS,
    dataset_id_for,
    dataset_ids_for_slice,
)
from src.routing.router import route_query
from src.schemas.concept import extract_concept
from src.schemas.slice import ComparisonSlice, parse_query_intent


def test_language_and_era_map_to_the_four_corpora():
    assert (
        dataset_id_for(language="English", period_start=1800, label="1800s")
        == LANGUAGE_DATASETS["kp"]["uuid"]
    )
    assert (
        dataset_id_for(language="English", period_start=2026, label="present")
        == LANGUAGE_DATASETS["wiki"]["uuid"]
    )
    assert (
        dataset_id_for(language="German", period_start=1900, label="1900s")
        == LANGUAGE_DATASETS["encyc"]["uuid"]
    )
    assert (
        dataset_id_for(language="French", period_start=1750, label="18th century")
        == LANGUAGE_DATASETS["diderot"]["uuid"]
    )


def test_marriage_slices_use_britannica_then_wikipedia():
    intent, errors = parse_query_intent(
        "How did a marriage look like in the 1800s compared to now?"
    )
    assert errors == []
    assert intent is not None
    assert [item.corpus_id for item in intent.slices] == [
        LANGUAGE_DATASETS["kp"]["uuid"],
        LANGUAGE_DATASETS["wiki"]["uuid"],
    ]


def test_cross_lingual_slices_use_encycnet_and_britannica():
    intent, errors = parse_query_intent(
        "Were descriptions of the US different in German sources compared to English sources in the 1900s?"
    )
    assert errors == []
    assert intent is not None
    by_lang = {item.language: item.corpus_id for item in intent.slices}
    assert by_lang["German"] == LANGUAGE_DATASETS["encyc"]["uuid"]
    assert by_lang["English"] == LANGUAGE_DATASETS["kp"]["uuid"]


DRESDEN_NICKNAMES = (
    "How do historical descriptions of the Dresden's cultural nicknames "
    "and the reasons given for them vary across time"
)


def test_query_without_years_defaults_to_knowledge_project_and_wikipedia():
    intent, errors = parse_query_intent(DRESDEN_NICKNAMES)
    assert errors == []
    assert intent is not None
    assert intent.dimension == "temporal"
    assert "Dresden" in intent.target_concept
    assert [item.label for item in intent.slices] == ["19th century", "present"]
    assert [item.corpus_id for item in intent.slices] == [
        LANGUAGE_DATASETS["kp"]["uuid"],
        LANGUAGE_DATASETS["wiki"]["uuid"],
    ]
    assert intent.slices[0].period_start == 1800
    assert intent.slices[0].period_end == 1899


def test_galileo_reporting_question_extracts_concept_and_default_periods():
    intent, errors = parse_query_intent(
        "How do historical accounts differ in reporting Galileo origin and family?"
    )
    assert errors == []
    assert intent is not None
    assert "Galileo" in intent.target_concept
    assert [item.label for item in intent.slices] == ["19th century", "present"]


SOCIALISM_ORIGIN = 'How do historical accounts vary in tracing the origin of "socialism"?'


def test_socialism_origin_question_extracts_quoted_concept():
    intent, errors = parse_query_intent(SOCIALISM_ORIGIN)
    assert errors == []
    assert intent is not None
    assert intent.target_concept.lower() == "socialism"
    assert intent.dimension == "temporal"
    assert [item.label for item in intent.slices] == ["19th century", "present"]
    first_use, first_errors = parse_query_intent(
        'Who used the term "socialism" for the first time?'
    )
    assert first_errors == []
    assert first_use is not None
    assert first_use.target_concept.lower() == "socialism"


BERLIN_CLIMATE = "How can the climate of Berlin in the 19th century be described?"


def test_single_period_climate_question_uses_one_knowledge_project_slice():
    intent, errors = parse_query_intent(BERLIN_CLIMATE)
    assert errors == []
    assert intent is not None
    assert intent.dimension == "descriptive"
    assert intent.target_concept.lower() == "climate of berlin"
    assert [item.label for item in intent.slices] == ["19th century"]
    assert [item.corpus_id for item in intent.slices] == [LANGUAGE_DATASETS["kp"]["uuid"]]
    paris, paris_errors = parse_query_intent(
        "How can the climate of Paris in the 19th century be described?"
    )
    assert paris_errors == []
    assert paris is not None
    assert paris.target_concept.lower() == "climate of paris"
    assert len(paris.slices) == 1


def test_generic_questions_extract_a_concept_without_name_lists():
    cases = {
        "How is liberty defined?": "liberty",
        "What is coffee?": "coffee",
        "Who invented the steam engine?": "steam engine",
        "How is democracy described in the 19th century?": "democracy",
        'How do historical accounts vary in tracing the origin of "socialism"?': "socialism",
        "How is Dresden defined?": "Dresden",
        "How is love defined?": "love",
        "How is philosophy defined broadly?": "philosophy",
    }
    for question, expected in cases.items():
        concept = extract_concept(question)
        assert expected.lower() in concept.lower(), (question, concept)
        intent, errors = parse_query_intent(question)
        assert errors == [], (question, errors)
        assert intent is not None
        assert expected.lower() in intent.target_concept.lower()
        assert intent.slices
        assert route_query(question).concept
    empty, empty_errors = parse_query_intent("   ")
    assert empty is None
    assert empty_errors


def test_benchmark_questions_all_parse():
    missing = []
    for row in load_benchmark():
        question = str(row.get("Question") or "").strip()
        if not question:
            continue
        intent, errors = parse_query_intent(question)
        if errors or intent is None or not intent.target_concept:
            missing.append((row.get("Question_ID"), question, errors))
    assert missing == []


def test_odin_today_adds_historical_corpus_slice():
    intent, errors = parse_query_intent(
        "How was Odin portrayed in earlier records compared to today?"
    )
    assert errors == []
    assert intent is not None
    assert intent.target_concept.lower() == "odin"
    assert [item.label for item in intent.slices] == ["19th century", "present"]
    assert [item.corpus_id for item in intent.slices] == [
        LANGUAGE_DATASETS["kp"]["uuid"],
        LANGUAGE_DATASETS["wiki"]["uuid"],
    ]


def test_dataset_ids_for_slice_prefers_existing_uuid():
    slice_ = ComparisonSlice(
        slice_id="slice_1",
        label="1800s",
        language="English",
        period_start=1800,
        period_end=1899,
        corpus_id=LANGUAGE_DATASETS["wiki"]["uuid"],
    )
    assert dataset_ids_for_slice(slice_) == [LANGUAGE_DATASETS["wiki"]["uuid"]]
