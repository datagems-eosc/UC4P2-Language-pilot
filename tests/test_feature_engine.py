from src.analytics.feature_engine import (
    attach_corpus_analysis,
    compute_collocations,
    compute_feature_metrics,
    extract_kwic,
)


def test_kwic_windows_and_collocation_counts():
    passages = [
        "Coverture bound wife and husband under property law.",
        "Coverture limited property ownership for the wife.",
    ]
    lines = extract_kwic(passages, ["coverture"], window=5)
    assert len(lines) == 2
    assert "husband" in lines[0]
    assert "wife" in lines[0]
    collocations = compute_collocations(passages, "coverture", top_k=5)
    assert collocations["property"] >= 1
    assert collocations["wife"] >= 1


def test_feature_metrics_are_keyed_by_slice():
    metrics = compute_feature_metrics(
        {
            "slice_1": ["Coverture shaped property and legal duty."],
            "slice_2": ["Shared property and equal legal standing."],
        },
        ["legal_standing"],
    )
    assert set(metrics) == {"slice_1", "slice_2"}
    assert "legal_standing" in metrics["slice_1"]
    assert "stance_distribution" in metrics["slice_2"]


def test_attach_corpus_analysis_keeps_remote_metadata():
    local = {"passage_count": 1}
    attach_corpus_analysis(
        local,
        {
            "query_time": 12.5,
            "results": [
                {
                    "content": "marriage",
                    "dataset_id": "ds",
                    "object_id": "obj",
                    "similarity": 0.7,
                    "metadata": {"pos": "NN", "lemma": "marriage"},
                }
            ],
        },
    )
    block = local["corpus_analysis"]
    assert block["source"] == "cross-dataset-discovery/corpus-analysis-search"
    assert block["hit_count"] == 1
    assert block["features"][0]["lemma"] == "marriage"


def test_measure_calls_corpus_analysis_search():
    from src.orchestration.pipeline import HistoricalQAOrchestrator
    from src.retrieval.multi_slice_retriever import CrossDatasetMultiSliceRetriever
    from src.schemas.slice import ComparisonSlice, ParsedQueryIntent
    from src.schemas.state import PipelineState

    class Client:
        def corpus_analysis_search(self, query, k=20, dataset_ids=None, search_mode="hybrid"):
            return {
                "query_time": 1,
                "results": [
                    {
                        "content": query,
                        "dataset_id": "ds",
                        "object_id": "o1",
                        "similarity": 0.9,
                        "metadata": {"kwic": ["marriage ceremony"]},
                    }
                ],
            }

    orch = HistoricalQAOrchestrator(retriever=CrossDatasetMultiSliceRetriever(client=Client(), k=2))
    state = PipelineState(
        question="How did a marriage look like in the 1800s compared to now?",
        query_id="q-features",
        status="retrieved",
        intent=ParsedQueryIntent(
            original_query="q",
            target_concept="marriage",
            dimension="temporal",
            slices=[
                ComparisonSlice(
                    slice_id="slice_1",
                    label="1800s",
                    language="English",
                    period_start=1800,
                    period_end=1899,
                )
            ],
        ),
        passages={"slice_1": [{"text": "Coverture bound wife and husband."}]},
        search_queries={"slice_1": "marriage 1800s"},
        knowledge_extension={"feature_lenses": ["legal_standing"]},
    )
    updated = orch.measure(state)
    analysis = updated.feature_metrics["slice_1"]["corpus_analysis"]
    assert analysis["source"] == "cross-dataset-discovery/corpus-analysis-search"
    assert analysis["features"][0]["kwic"] == ["marriage ceremony"]
    assert "legal_standing" in updated.feature_metrics["slice_1"]


def test_measure_soft_fails_when_corpus_analysis_times_out():
    from src.orchestration.pipeline import HistoricalQAOrchestrator
    from src.retrieval.multi_slice_retriever import CrossDatasetMultiSliceRetriever
    from src.schemas.slice import ComparisonSlice, ParsedQueryIntent
    from src.schemas.state import PipelineState

    class Client:
        def corpus_analysis_search(self, query, k=20, dataset_ids=None, search_mode="hybrid"):
            raise TimeoutError("The read operation timed out")

    orch = HistoricalQAOrchestrator(retriever=CrossDatasetMultiSliceRetriever(client=Client(), k=2))
    state = PipelineState(
        question="How did a marriage look like in the 1800s compared to now?",
        query_id="q-timeout",
        status="retrieved",
        intent=ParsedQueryIntent(
            original_query="q",
            target_concept="marriage",
            dimension="temporal",
            slices=[
                ComparisonSlice(
                    slice_id="slice_1",
                    label="1800s",
                    language="English",
                    period_start=1800,
                    period_end=1899,
                )
            ],
        ),
        passages={"slice_1": [{"text": "Coverture bound wife and husband."}]},
        search_queries={"slice_1": "marriage 1800s"},
        knowledge_extension={"feature_lenses": ["legal_standing"]},
    )
    updated = orch.measure(state)
    assert updated.status == "features_computed"
    analysis = updated.feature_metrics["slice_1"]["corpus_analysis"]
    assert "timed out" in analysis["error"].lower()
    assert "legal_standing" in updated.feature_metrics["slice_1"]
