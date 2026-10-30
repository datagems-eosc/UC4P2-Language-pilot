from fastapi.testclient import TestClient

from src.app.main import app
from src.app.schemas import QueryRequest
from src.evaluation.judge import resolve_judge_target
from src.llm import default_judge_model, default_pipeline_model


def test_llm_options_endpoint_lists_defaults():
    client = TestClient(app)
    response = client.get("/llm/options")
    assert response.status_code == 200
    body = response.json()
    assert body["default_llm_model"] == default_pipeline_model()
    assert body["default_judge_llm_model"] == default_judge_model()
    assert body["default_llm_model"] in body["models"]
    assert body["default_judge_llm_model"] in body["models"]


def test_query_request_accepts_model_overrides():
    body = QueryRequest(
        query="How does marriage shift over time?",
        llm_model="kimi-k2.6",
        judge_llm_model="qwen3",
    )
    assert body.llm_model == "kimi-k2.6"
    assert body.judge_llm_model == "qwen3"


def test_resolve_judge_respects_request_models(monkeypatch):
    monkeypatch.setattr(
        "src.evaluation.judge.credentials_present_for",
        lambda provider: provider == "scayle",
    )
    target = resolve_judge_target(
        pipeline_model="qwen3",
        judge_model="glm-5.3-flash",
    )
    assert target == ("scayle", "glm-5.3-flash")
    swapped = resolve_judge_target(
        pipeline_model="glm-5.3-flash",
        judge_model="glm-5.3-flash",
    )
    assert swapped is not None
    assert swapped[1] != "glm-5.3-flash"
