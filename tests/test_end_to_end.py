from src.constraints.comparative import DisambiguationAPIError, HistoricalComparativeConstraints
from src.orchestration.pipeline import HistoricalQAOrchestrator
from src.retrieval.multi_slice_retriever import MockMultiSliceRetriever
from src.schemas.benchmark import BenchmarkOutput

MARRIAGE = "How did a marriage look like in the 1800s compared to now?"
THREE = "How did a marriage look like in the 1800s, the 1900s, and now?"


class OfflineDisambiguation:
    def disambiguate_language(self, query, llm_model=None):
        raise DisambiguationAPIError("offline")


def _run(question: str) -> BenchmarkOutput:
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=OfflineDisambiguation(),
        retriever=MockMultiSliceRetriever(),
    )
    output = pipeline(question=question, query_id="q-test")
    return BenchmarkOutput.model_validate(output.model_dump())


def test_two_slice_output_matches_benchmark_schema():
    output = _run(MARRIAGE)
    assert output.query_id == "q-test"
    assert len(output.slices_evaluated) == 2
    assert {item.slice_id for item in output.slices_evaluated} == {"slice_1", "slice_2"}
    assert "husband" in output.knowledge_extension["thematic_facets"]
    assert "coverture" in output.knowledge_extension["slice_1"]
    assert set(output.feature_metrics) == {"slice_1", "slice_2"}
    assert {item.slice_id for item in output.grounded_citations} == {"slice_1", "slice_2"}
    assert "[ref_1]" in output.synthesized_answer


def test_three_slice_output_matches_benchmark_schema():
    output = _run(THREE)
    assert len(output.slices_evaluated) == 3
    assert [item.slice_id for item in output.slices_evaluated] == ["slice_1", "slice_2", "slice_3"]
    assert set(output.feature_metrics) == {"slice_1", "slice_2", "slice_3"}
    assert len(output.grounded_citations) == 3
    BenchmarkOutput.model_validate(output.model_dump())


def test_scripted_service_payload_still_runs():
    class Scripted:
        def disambiguate_language(self, query, llm_model=None):
            return HistoricalComparativeConstraints.from_query(query).to_api_dict()

    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=Scripted(),
        retriever=MockMultiSliceRetriever(),
    )
    state = pipeline.run(MARRIAGE, query_id="q-marriage")
    assert state.status == "ok"
    assert state.disambiguation_source == "query-disambiguation-api"
    assert state.output is not None
    BenchmarkOutput.model_validate(state.output.model_dump())
