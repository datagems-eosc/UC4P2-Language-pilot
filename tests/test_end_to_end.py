from src.constraints.comparative import DisambiguationAPIError, HistoricalComparativeConstraints
from src.orchestration.pipeline import (
    HistoricalQAOrchestrator,
    _answer_is_grounded,
    _publish_cited_only,
)
from src.retrieval.multi_slice_retriever import MockMultiSliceRetriever
from src.schemas.benchmark import BenchmarkOutput, Citation

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
    assert "marriage" in output.knowledge_extension["thematic_facets"]
    assert "definition" in output.knowledge_extension["thematic_facets"]
    assert output.knowledge_extension["slice_1"]
    assert set(output.feature_metrics) == {"slice_1", "slice_2"}
    assert {item.slice_id for item in output.grounded_citations} == {"slice_1", "slice_2"}
    assert "[ref_1]" in output.synthesized_answer
    cited = {item.citation_id for item in output.grounded_citations if item.used_in_answer}
    assert cited
    assert all(item.source_document for item in output.grounded_citations)


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


def test_grounded_citations_drop_unused_hits_and_renumber():
    citations = [
        Citation(citation_id="ref_1", slice_id="slice_1", source_document="a", text_snippet="old"),
        Citation(citation_id="ref_6", slice_id="slice_2", source_document="b", text_snippet="jewel box"),
        Citation(citation_id="ref_9", slice_id="slice_2", source_document="c", text_snippet="collections"),
    ]
    answer, published = _publish_cited_only(
        "Dresden was called the Jewel Box [ref_6]. The collections began in the 16th century [ref_9].",
        citations,
    )
    assert "[ref_1]" in answer and "[ref_2]" in answer
    assert "[ref_6]" not in answer and "[ref_9]" not in answer
    assert [item.citation_id for item in published] == ["ref_1", "ref_2"]
    assert [item.source_document for item in published] == ["b", "c"]
    assert all(item.used_in_answer for item in published)


def test_answer_must_cite_retrieved_refs():
    citations = [
        Citation(
            citation_id="ref_1",
            slice_id="slice_1",
            source_document="doc-a",
            text_snippet="Coverture bound the wife.",
        )
    ]
    assert _answer_is_grounded("In the 1800s coverture applied [ref_1].", citations, [])
    assert not _answer_is_grounded("Modern marriage is about love.", citations, [])
    assert not _answer_is_grounded("A claim [ref_9].", citations, [])
    assert not _answer_is_grounded(
        "In the present, people marry for love.",
        citations,
        ["present"],
    )
    assert _answer_is_grounded(
        "1800s: coverture [ref_1]. present: no indexed passage was returned.",
        citations,
        ["present"],
    )
