from src.app.runner import run_compare
from src.constraints.comparative import HistoricalComparativeConstraints


MARRIAGE = "How did a marriage look like in the 1800s compared to now?"


class ScriptedDisambiguation:
    def disambiguate_language(self, query, llm_model=None):
        return HistoricalComparativeConstraints.from_query(query).to_api_dict()


class ScriptedRetrieval:
    def search(self, query, k=5, dataset_ids=None, search_mode="hybrid"):
        text = "In this period marriage is discussed through coverture and legal rights."
        return {
            "query_time": "1",
            "results": [
                {
                    "content": text,
                    "dataset_id": "pilot2-corpus",
                    "object_id": "p1",
                    "similarity": 0.5,
                }
            ],
        }


def test_run_compare_returns_answer(monkeypatch):
    from src.orchestration import graph as graph_mod

    original = graph_mod.stream_steps

    def fake_stream(question, **kwargs):
        kwargs["disambiguation_client"] = ScriptedDisambiguation()
        kwargs["retrieval_client"] = ScriptedRetrieval()
        return original(question, **kwargs)

    monkeypatch.setattr("src.app.runner.stream_steps", fake_stream)
    payload = run_compare(MARRIAGE, query_id="q-api")
    assert payload["status"] == "ok"
    assert payload["concept"] == "marriage"
    assert payload["passages"]["slice_1"]
    assert payload["search_queries"]
    assert payload["synthesized_answer"]
    assert payload["benchmark"]["query_id"] == "q-api"
    assert "retrieve_slices" in payload["steps"]
    names = [item["name"] for item in payload["pipeline"]]
    assert names == [
        "route",
        "disambiguate",
        "extend_knowledge",
        "decompose",
        "retrieve_slices",
        "compute_features",
        "synthesize",
        "export_benchmark",
    ]
    assert all(item["outcome"] == "ok" for item in payload["pipeline"])
    assert payload["pipeline"][4]["output"]["passages"]


def test_compare_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from src.app.main import app
    from src.orchestration import graph as graph_mod

    original = graph_mod.stream_steps

    def fake_stream(question, **kwargs):
        kwargs["disambiguation_client"] = ScriptedDisambiguation()
        kwargs["retrieval_client"] = ScriptedRetrieval()
        return original(question, **kwargs)

    monkeypatch.setattr("src.app.runner.stream_steps", fake_stream)
    monkeypatch.setenv("AUTH_DISABLED", "true")
    client = TestClient(app)
    response = client.post("/compare", json={"query": MARRIAGE, "query_id": "q-http"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["synthesized_answer"]
    assert body["pipeline"][0]["name"] == "route"
    assert body["pipeline"][-1]["name"] == "export_benchmark"
    health = client.get("/health")
    assert health.json() == {"status": "healthy"}
