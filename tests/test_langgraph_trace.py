from src.constraints.comparative import HistoricalComparativeConstraints
from src.orchestration.graph import stream_steps

MARRIAGE = "How did a marriage look like in the 1800s compared to now?"
PRE_1800 = "How did a marriage look like in the 1500s compared to now?"


class ScriptedDisambiguation:
    def __init__(self, payload):
        self.payload = payload
        self.queries = []

    def disambiguate_language(self, query, llm_model=None):
        self.queries.append(query)
        return self.payload


class ScriptedRetrieval:
    def search(self, query, k=5, dataset_ids=None, search_mode="hybrid"):
        if "1800" in query:
            text = "In the 1800s a wife lived under coverture and had few property rights."
            object_id = "a1"
        else:
            text = "Today marriage is framed through shared domestic roles and legal rights."
            object_id = "b1"
        return {
            "query_time": "1",
            "results": [
                {
                    "content": text,
                    "dataset_id": "pilot2-corpus",
                    "object_id": object_id,
                    "similarity": 0.4,
                }
            ],
        }


def test_comparative_trace_emits_each_step():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(MARRIAGE).to_api_dict()
    )
    events = list(
        stream_steps(
            MARRIAGE,
            query_id="q-marriage",
            disambiguation_client=client,
            retrieval_client=ScriptedRetrieval(),
        )
    )
    assert [event["step"] for event in events] == [
        "route",
        "disambiguate",
        "extend_knowledge",
        "generate_subquestions",
        "decompose",
        "retrieve_slices",
        "compute_features",
        "synthesize",
        "evaluate_answer",
        "export_benchmark",
    ]
    by_step = {event["step"]: event["output"] for event in events}
    assert by_step["route"]["domain"] == "comparative"
    assert by_step["disambiguate"]["concept"] == "marriage"
    assert by_step["disambiguate"]["comparison_type"] == "temporal"
    facets = by_step["extend_knowledge"]["expansion"]["thematic_facets"]
    assert "marriage" in facets
    assert "definition" in facets
    assert "husband" not in facets
    assert by_step["generate_subquestions"]["generated_subquestions"]
    assert any(
        item["source"] == "facet" and "definition" in item["question"]
        for item in by_step["generate_subquestions"]["generated_subquestions"]
    )
    assert "#1" in by_step["decompose"]["qdmr"][2]["instruction"]
    assert "metrics" in by_step["evaluate_answer"]["nlg_evaluation"]
    assert by_step["evaluate_answer"]["nlg_evaluation"]["matched"] is True
    assert by_step["evaluate_answer"]["nlg_evaluation"]["question_id"] == "9"
    assert by_step["retrieve_slices"]["passages"]["slice_1"][0]["text_snippet"]
    assert by_step["retrieve_slices"]["passages"]["slice_2"][0]["text_snippet"]
    lenses = by_step["extend_knowledge"]["expansion"]["feature_lenses"]
    slice_metrics = by_step["compute_features"]["feature_metrics"]["slice_1"]
    assert any(lens in slice_metrics for lens in lenses)
    assert "coverture" in by_step["synthesize"]["synthesized_answer"]
    assert by_step["export_benchmark"]["benchmark"]["query_id"] == "q-marriage"
    assert client.queries == [MARRIAGE]


def test_trace_stops_after_a_named_step():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(MARRIAGE).to_api_dict()
    )
    events = list(
        stream_steps(
            MARRIAGE,
            until="decompose",
            disambiguation_client=client,
            retrieval_client=ScriptedRetrieval(),
        )
    )
    assert [event["step"] for event in events] == [
        "route",
        "disambiguate",
        "extend_knowledge",
        "generate_subquestions",
        "decompose",
    ]


def test_pre_1800_stops_at_disambiguation():
    client = ScriptedDisambiguation(
        HistoricalComparativeConstraints.from_query(PRE_1800).to_api_dict()
    )
    retrieval = ScriptedRetrieval()
    events = list(
        stream_steps(
            PRE_1800,
            disambiguation_client=client,
            retrieval_client=retrieval,
        )
    )
    assert [event["step"] for event in events] == ["route", "disambiguate"]
    assert events[-1]["output"]["status"] == "clarification"
    assert "1500s" in events[-1]["output"]["clarification"]
