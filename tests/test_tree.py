from src.app.tree import presentation_tree, tree_markup, tree_page


def test_presentation_tree_is_pipeline_first_to_last():
    payload = {
        "feature_metrics": {"huge": True},
        "synthesized_answer": "Marriage was a contract [ref_1].",
        "question": "How did marriage look?",
        "status": "ok",
        "pipeline": [
            {"step": 1, "name": "route", "title": "Route the question", "outcome": "ok", "summary": "routed", "output": {}},
            {"step": 2, "name": "synthesize", "title": "Synthesize a grounded answer", "outcome": "ok", "summary": "wrote", "output": {}},
        ],
        "result": {"name": "synthesize"},
    }
    ordered = presentation_tree(payload)
    assert list(ordered)[:4] == ["question", "status", "pipeline", "synthesized_answer"]
    assert [item["name"] for item in ordered["pipeline"]] == ["route", "synthesize"]
    assert "feature_metrics" not in ordered
    assert "result" not in ordered


def test_tree_markup_lists_steps_in_order():
    markup = tree_markup(
        {
            "question": "Q",
            "status": "ok",
            "pipeline": [
                {"step": 1, "name": "route", "title": "Route the question", "outcome": "ok", "summary": "A", "output": {"domain": "comparative"}},
                {"step": 2, "name": "decompose", "title": "Decompose into sub-questions", "outcome": "ok", "summary": "B", "output": {}},
            ],
        }
    )
    assert markup.index("Route the question") < markup.index("Decompose into sub-questions")
    assert "class=\"step ok\"" in markup


def test_tree_endpoint_renders_posted_json(monkeypatch):
    from fastapi.testclient import TestClient
    from src.app.main import app

    monkeypatch.setenv("AUTH_DISABLED", "true")
    client = TestClient(app)
    page = client.get("/tree")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "ThematicExploration" in page.text
    rendered = client.post(
        "/tree",
        json={
            "question": "How did marriage look?",
            "status": "ok",
            "pipeline": [
                {"step": 1, "name": "route", "title": "Route the question", "outcome": "ok", "summary": "routed", "output": {}},
                {"step": 2, "name": "disambiguate", "title": "Disambiguate", "outcome": "ok", "summary": "slices", "output": {}},
            ],
            "synthesized_answer": "A contract [ref_1].",
        },
    )
    assert rendered.status_code == 200
    html = rendered.text
    assert html.index("Route the question") < html.index("Disambiguate")
    assert "A contract [ref_1]." in html
    assert tree_page({"question": "Q"})  # page still builds
