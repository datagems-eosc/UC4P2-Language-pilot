from src.retrieval.corpora import (
    LANGUAGE_DATASETS,
    dataset_id_for,
    dataset_ids_for_slice,
)
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
