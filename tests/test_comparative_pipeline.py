import json
from urllib.request import Request

from src.constraints.comparative import (
    DisambiguationAPIError,
    HistoricalComparativeConstraints,
    QueryDisambiguationClient,
)
from src.orchestration.pipeline import HistoricalQAOrchestrator
from src.orchestration.slice_executor import CrossDatasetDiscoveryClient
from src.retrieval.multi_slice_retriever import CrossDatasetMultiSliceRetriever
from src.schemas.benchmark import BenchmarkOutput


MARRIAGE = "How did a marriage look like in the 1800s compared to now?"
US_SOURCES = (
    "Were descriptions of the US different in German sources "
    "compared to English sources in the 1900s?"
)
PRE_1800 = "How did a marriage look like in the 1500s compared to now?"


class ScriptedDisambiguation:
    def __init__(self, payload):
        self.payload = payload
        self.queries = []

    def disambiguate_language(self, query, llm_model=None):
        self.queries.append(query)
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ScriptedRetrieval:
    def __init__(self):
        self.queries = []

    def search(self, query, k=5, dataset_ids=None, search_mode="hybrid"):
        self.queries.append(query)
        if "German" in query or "1800" in query:
            text = (
                "In this period a wife lived under coverture and property rights "
                "remained with the husband."
            )
            object_id = "slice-1-passage"
        else:
            text = (
                "Later accounts frame marriage through shared domestic roles "
                "and equal legal rights."
            )
            object_id = "slice-2-passage"
        return {
            "query_time": "3",
            "results": [
                {
                    "content": text,
                    "dataset_id": "pilot2-corpus",
                    "object_id": object_id,
                    "similarity": 0.42,
                }
            ],
        }


BERLIN_CLIMATE = "How can the climate of Berlin in the 19th century be described?"


def test_single_period_climate_gate_keeps_one_slice():
    gate = HistoricalComparativeConstraints.from_query(BERLIN_CLIMATE)
    assert gate.clarification() is None
    assert gate.comparison_type == "descriptive"
    assert gate.target_concepts == ["climate of Berlin"]
    assert [item.label for item in gate.slices] == ["19th century"]
    assert len(gate.slices) == 1


def test_resolve_trusts_remote_descriptive_payload():
    client = ScriptedDisambiguation(
        {
            "proceed": True,
            "comparison_type": "descriptive",
            "target_concepts": ["climate of Berlin"],
            "slices": [
                {
                    "slice_id": "slice_1",
                    "label": "19th century",
                    "start_year": 1801,
                    "end_year": 1900,
                    "language": "English",
                },
            ],
        }
    )
    pipeline = HistoricalQAOrchestrator(disambiguation_client=client)
    state = pipeline.resolve(BERLIN_CLIMATE)
    assert state.status == "disambiguated"
    assert state.disambiguation_source == "query-disambiguation-api"
    assert state.intent is not None
    assert state.intent.dimension == "descriptive"
    assert [item.label for item in state.intent.slices] == ["19th century"]


def test_single_period_pipeline_retrieves_one_slice():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(BERLIN_CLIMATE).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
    )
    state = pipeline.run(BERLIN_CLIMATE, query_id="34")
    assert state.status == "ok"
    assert state.intent is not None
    assert len(state.intent.slices) == 1
    assert len(retrieval.queries) == 1
    assert state.output is not None
    assert state.output.synthesized_answer


SOCIALISM_ORIGIN = 'How do historical accounts vary in tracing the origin of "socialism"?'


def test_socialism_origin_gate_extracts_concept_and_default_slices():
    gate = HistoricalComparativeConstraints.from_query(SOCIALISM_ORIGIN)
    assert gate.clarification() is None
    assert gate.comparison_type == "temporal"
    assert [item.lower() for item in gate.target_concepts] == ["socialism"]
    assert [item.label for item in gate.slices] == ["19th century", "present"]


def test_missing_periods_use_indexed_corpus_eras():
    gate = HistoricalComparativeConstraints.from_query(
        "How do historical descriptions of the Dresden's cultural nicknames "
        "and the reasons given for them vary across time"
    )
    assert gate.clarification() is None
    assert gate.comparison_type == "temporal"
    assert [item.label for item in gate.slices] == ["19th century", "present"]
    assert gate.slices[0].start_year == 1800
    assert gate.slices[1].label == "present"


def test_remote_reject_surfaces_clarification_without_local_override():
    client = ScriptedDisambiguation(
        {
            "proceed": False,
            "constraint_errors": [
                "A comparison needs at least two slices. Provide two or more periods or source languages."
            ],
            "clarification": (
                "This historical comparative query cannot be executed against the indexed archives. "
                "Please name the concept and restrict every slice to indexed sources from 1800 onward."
            ),
            "slices": [],
        }
    )
    query = (
        "How do historical descriptions of the Dresden's cultural nicknames "
        "and the reasons given for them vary across time"
    )
    pipeline = HistoricalQAOrchestrator(disambiguation_client=client)
    state = pipeline.resolve(query)
    assert state.status == "clarification"
    assert state.disambiguation_source == "query-disambiguation-api"
    assert state.intent is None
    assert "indexed archives" in (state.clarification or "")


def test_local_gate_flags_pre_1800_archives():
    gate = HistoricalComparativeConstraints.from_query(PRE_1800)
    errors = gate.validate_boundaries()
    assert errors
    assert any("1500s" in error for error in errors)
    assert gate.clarification()
    assert "1800" in gate.clarification()


def test_pipeline_halts_when_disambiguation_api_rejects_archive():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(PRE_1800).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
    )
    result = pipeline.run(PRE_1800)
    assert result.status == "clarification"
    assert "1500s" in (result.clarification or "")
    assert client.queries == [PRE_1800]
    assert retrieval.queries == []


def test_comparative_pipeline_retrieves_and_exports_benchmark():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(MARRIAGE).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
    )
    state = pipeline.run(MARRIAGE, query_id="q-marriage")
    assert state.status == "ok"
    assert state.disambiguation_source == "query-disambiguation-api"
    assert client.queries == [MARRIAGE]
    assert len(retrieval.queries) == 2
    assert "#1" in state.sub_tasks[-1] and "#2" in state.sub_tasks[-1]
    assert all("Retrieve" not in task for task in state.sub_tasks)
    record = BenchmarkOutput.model_validate(state.output)
    assert record.query_id == "q-marriage"
    assert "marriage" in record.knowledge_extension["thematic_facets"]
    assert "definition" in record.knowledge_extension["thematic_facets"]
    assert set(record.feature_metrics) == {"slice_1", "slice_2"}
    lenses = record.knowledge_extension["feature_lenses"]
    assert lenses
    assert all(lens in record.feature_metrics["slice_1"] for lens in lenses)
    assert {item.slice_id for item in record.grounded_citations} == {"slice_1", "slice_2"}
    assert record.grounded_citations[0].citation_id == "ref_1"
    assert "coverture" in record.synthesized_answer


def test_extension_questions_are_retrieved_without_changing_decomposition():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(MARRIAGE).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
        use_extension_questions=True,
    )
    state = pipeline.run(MARRIAGE, query_id="q-marriage-ke")
    assert state.status == "ok"
    assert state.use_extension_questions
    assert not any("definition" in task.lower() for task in state.sub_tasks)
    assert any("differ across" in task.lower() for task in state.sub_tasks)
    assert len(retrieval.queries) > 2
    assert any("definition" in query.lower() for query in retrieval.queries)
    assert all(query == query.strip() for query in retrieval.queries)
    hits = sum(len(items) for items in state.passages.values())
    assert hits >= 2
    assert state.output is not None
    assert state.output.synthesized_answer
    assert {item.slice_id for item in state.output.grounded_citations} == {"slice_1", "slice_2"}


def test_cross_lingual_pipeline_keeps_both_languages():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(US_SOURCES).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
    )
    state = pipeline.run(US_SOURCES)
    assert state.status == "ok"
    assert state.disambiguation["comparison_type"] == "cross_lingual"
    joined_lemmas = " ".join(
        " ".join(words) for words in state.knowledge_extension.values()
    )
    assert "Amerika" not in joined_lemmas
    assert "German" in joined_lemmas
    joined = " ".join(retrieval.queries)
    assert "German" in joined


def test_api_outage_falls_back_to_local_archive_gate():
    client = ScriptedDisambiguation(DisambiguationAPIError("down"))
    retrieval = ScriptedRetrieval()
    pipeline = HistoricalQAOrchestrator(
        disambiguation_client=client,
        retriever=CrossDatasetMultiSliceRetriever(client=retrieval),
    )
    result = pipeline.run(PRE_1800)
    assert result.status == "clarification"
    assert result.disambiguation_source == "local-fallback"
    assert retrieval.queries == []


def test_disambiguation_client_posts_language_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request: Request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"result": {"proceed": True, "target_concepts": ["marriage"]}}
                ).encode("utf-8")

        return _Response()

    monkeypatch.setattr("src.constraints.comparative.urllib.request.urlopen", fake_urlopen)
    client = QueryDisambiguationClient(
        base_url="http://disambiguation.internal",
        token="token-1",
        use_llm=True,
    )
    payload = client.disambiguate_language("How did a marriage look like in the 1800s compared to now?")
    assert captured["url"] == "http://disambiguation.internal/query_disambiguation/language"
    assert captured["body"]["use_llm"] is True
    assert captured["auth"] == "Bearer token-1"
    assert payload["proceed"] is True


def test_search_query_uses_sub_question():
    from src.retrieval.multi_slice_retriever import search_query_for_slice
    from src.schemas.slice import ComparisonSlice

    slice_ = ComparisonSlice(
        slice_id="slice_1",
        label="1800s",
        language="English",
        period_start=1800,
        period_end=1899,
    )
    query = search_query_for_slice(
        "marriage",
        slice_,
        ["coverture"],
        ["#1 How is marriage described in the 1800s?", "#2 How does it differ across #1?"],
    )
    assert query == "How is marriage described in the 1800s?"
    assert "coverture" not in query


def test_retrieval_client_posts_search_endpoint(monkeypatch):
    captured = {}

    def fake_urlopen(request: Request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["auth"] = request.get_header("Authorization")

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"query_time": "1", "results": []}).encode("utf-8")

        return _Response()

    monkeypatch.setattr(
        "src.orchestration.slice_executor.urllib.request.urlopen",
        fake_urlopen,
    )
    client = CrossDatasetDiscoveryClient(
        base_url="https://datagems-dev.scayle.es/cross-dataset-discovery",
        token="jwt-token",
        search_mode="hybrid",
    )
    payload = client.search("marriage 1800s", k=5, dataset_ids=["dataset-1"])
    assert captured["url"] == "https://datagems-dev.scayle.es/cross-dataset-discovery/search/"
    assert captured["body"] == {
        "query": "marriage 1800s",
        "k": 5,
        "dataset_ids": ["dataset-1"],
        "search_mode": "hybrid",
    }
    assert captured["auth"] == "Bearer jwt-token"
    assert payload["results"] == []
