from pathlib import Path

from src.app.run_memory import (
    attach_memory_meta,
    load_run,
    memory_key,
    normalize_question,
    save_run,
    should_store,
)


def test_normalize_question_collapses_whitespace_and_case():
    assert normalize_question("  How was Odin  portrayed? ") == "how was odin portrayed?"


def test_memory_key_stable_for_same_request():
    a = memory_key("How was Odin portrayed?", query_id="23", k=5, decompose_mode="few-shot", until=None)
    b = memory_key("how was   odin portrayed?", query_id="23", k=5, decompose_mode="few-shot", until=None)
    c = memory_key("How was Odin portrayed?", query_id="23", k=5, decompose_mode="few-shot", until="decompose")
    d = memory_key(
        "How was Odin portrayed?",
        query_id="23",
        k=5,
        decompose_mode="few-shot",
        until=None,
        use_extension_questions=True,
    )
    assert a == b
    assert a != c
    assert a != d


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_MEMORY_DIR", str(tmp_path))
    key = memory_key("Q", query_id="1", k=5, decompose_mode="few-shot", until=None)
    result = {"status": "ok", "question": "Q", "pipeline": [{"name": "route", "outcome": "ok"}]}
    meta = save_run(key, result, request={"query": "Q"})
    assert Path(meta["path"]).is_file()
    loaded = load_run(key)
    assert loaded is not None
    assert loaded["result"]["status"] == "ok"
    assert loaded["key"] == key


def test_should_store_skips_timeouts():
    assert should_store({"status": "ok"})
    assert should_store({"status": "clarification"})
    assert not should_store({"status": "timeout"})
    assert not should_store({"status": "error"})


def test_attach_memory_meta():
    payload = attach_memory_meta({"status": "ok"}, hit=True, key="abc", stored_at="t", path="/x")
    assert payload["memory"] == {"hit": True, "key": "abc", "stored_at": "t", "path": "/x"}


def test_thematic_exploration_uses_memory(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from src.app.main import app

    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("RUN_MEMORY_ENABLED", "true")
    monkeypatch.setenv("RUN_MEMORY_DIR", str(tmp_path))

    calls = {"n": 0}

    def fake_run_compare(question, **kwargs):
        calls["n"] += 1
        return {
            "query_id": "q1",
            "question": question,
            "status": "ok",
            "last_step": "export_benchmark",
            "pipeline": [
                {
                    "step": 1,
                    "name": "route",
                    "title": "Route",
                    "outcome": "ok",
                    "summary": "routed",
                    "output": {},
                }
            ],
            "steps": ["route"],
            "synthesized_answer": f"answer-{calls['n']}",
        }

    monkeypatch.setattr("src.app.main.run_compare", fake_run_compare)
    client = TestClient(app)

    first = client.post(
        "/ThematicExploration",
        json={"query": "How was Odin portrayed?", "query_id": "23", "k": 5},
    )
    assert first.status_code == 200, first.text
    body1 = first.json()
    assert body1["memory"]["hit"] is False
    assert body1["synthesized_answer"] == "answer-1"
    assert calls["n"] == 1

    second = client.post(
        "/ThematicExploration",
        json={"query": "How was Odin portrayed?", "query_id": "23", "k": 5},
    )
    assert second.status_code == 200
    body2 = second.json()
    assert body2["memory"]["hit"] is True
    assert body2["synthesized_answer"] == "answer-1"
    assert calls["n"] == 1

    refreshed = client.post(
        "/ThematicExploration",
        json={
            "query": "How was Odin portrayed?",
            "query_id": "23",
            "k": 5,
            "refresh": True,
        },
    )
    assert refreshed.status_code == 200
    body3 = refreshed.json()
    assert body3["memory"]["hit"] is False
    assert body3["synthesized_answer"] == "answer-2"
    assert calls["n"] == 2
