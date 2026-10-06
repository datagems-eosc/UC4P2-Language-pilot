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
        "generate_subquestions",
        "decompose",
        "retrieve_slices",
        "compute_features",
        "synthesize",
        "evaluate_answer",
        "export_benchmark",
    ]
    assert all(item["outcome"] == "ok" for item in payload["pipeline"])
    assert payload["pipeline"][5]["output"]["passages"]
    assert payload["generated_subquestions"]
    assert "nlg_evaluation" in payload


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
    response = client.post("/ThematicExploration", json={"query": MARRIAGE, "query_id": "q-http"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["synthesized_answer"]
    assert body["pipeline"][0]["name"] == "route"
    assert body["pipeline"][-1]["name"] == "export_benchmark"
    alias = client.post("/compare", json={"query": MARRIAGE, "query_id": "q-alias"})
    assert alias.status_code == 200, alias.text
    assert alias.json()["status"] == "ok"
    health = client.get("/health")
    assert health.json() == {"status": "healthy"}
    catalog = client.get("/steps")
    assert catalog.status_code == 200
    paths = [item["path"] for item in catalog.json()["steps"]]
    assert "POST /steps/route" in paths
    routed = client.post("/steps/route", json={"query": MARRIAGE, "query_id": "q-route"})
    assert routed.status_code == 200, routed.text
    route_body = routed.json()
    assert route_body["status"] == "ok"
    assert route_body["last_step"] == "route"
    assert route_body["result"]["name"] == "route"
    assert route_body["result"]["outcome"] == "ok"
    assert len(route_body["pipeline"]) == 1
    sliced = client.post("/steps/disambiguate", json={"query": MARRIAGE, "query_id": "q-dis"})
    assert sliced.status_code == 200, sliced.text
    dis_body = sliced.json()
    assert dis_body["last_step"] == "disambiguate"
    assert dis_body["result"]["output"]["slices"]
    assert dis_body["concept"] == "marriage"


def test_decompose_mode_on_thematic_exploration(monkeypatch):
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
    response = client.post(
        "/steps/decompose",
        json={"query": MARRIAGE, "query_id": "q-cot", "decompose_mode": "CoT"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decompose_mode"] == "cot"
    assert body["result"]["output"]["decompose_mode"] == "cot"
    assert "cot" in body["result"]["summary"]
    bad = client.post("/ThematicExploration", json={"query": MARRIAGE, "decompose_mode": "mipro"})
    assert bad.status_code == 422
