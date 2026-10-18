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
    keys = list(ordered)
    assert keys.index("question") < keys.index("pipeline") < keys.index("synthesized_answer")
    assert [item["name"] for item in ordered["pipeline"]] == ["route", "synthesize"]
    assert "feature_metrics" not in ordered
    assert "result" not in ordered


def test_presentation_tree_promotes_decompose_and_retrieve_details():
    payload = {
        "question": "How was Odin portrayed?",
        "status": "ok",
        "slices": [
            {
                "slice_id": "slice_1",
                "label": "19th century",
                "corpus_id": "d84d1a2e-127d-4393-91d0-afb7e4fd9c68",
            }
        ],
        "pipeline": [
            {
                "step": 1,
                "name": "decompose",
                "title": "Decompose",
                "outcome": "ok",
                "summary": "qdmr",
                "output": {
                    "qdmr": [{"step": 1, "instruction": "#1 Who is Odin?"}],
                    "decompose_mode": "few-shot",
                },
            },
            {
                "step": 2,
                "name": "retrieve_slices",
                "title": "Retrieve",
                "outcome": "ok",
                "summary": "hits",
                "output": {
                    "search_queries": {"slice_1": "Odin"},
                    "passages": {
                        "slice_1": [
                            {
                                "dataset_id": "d84d1a2e-127d-4393-91d0-afb7e4fd9c68",
                                "doc_id": "d1",
                                "similarity": 0.5,
                                "text": "Odin appears in the calendar.",
                            }
                        ]
                    },
                },
            },
        ],
    }
    ordered = presentation_tree(payload)
    decompose, retrieve = ordered["pipeline"]
    assert decompose["decomposed_questions"][0]["instruction"] == "#1 Who is Odin?"
    assert "19th century · 19th C. Knowledge Project (Britannica)" in retrieve["retrieved_passages"]
    rows = retrieve["retrieved_passages"]["19th century · 19th C. Knowledge Project (Britannica)"]
    assert rows[0]["corpus"] == "19th C. Knowledge Project (Britannica)"
    assert "Odin" in rows[0]["text"]


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
    assert "tree/token" in page.text
    assert "mintAccessToken" in page.text
    assert "Getting access token" in page.text
    assert "id=\"token\"" not in page.text
    assert "ThematicExploration/stream" in page.text
    assert "function apiUrl" in page.text
    assert "Stream interrupted" in page.text
    assert "Running pipeline" in page.text
    assert "tree/questions" in page.text
    assert "id=\"drawer\"" in page.text
    assert "Benchmark questions" in page.text
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
    assert "[ref_1]" in html
    assert "A contract" in html
    assert tree_page({"question": "Q"})  # page still builds


def test_tree_markup_links_answer_refs_to_citations():
    markup = tree_markup(
        {
            "question": "How did marriage look?",
            "status": "ok",
            "pipeline": [
                {
                    "step": 1,
                    "name": "synthesize",
                    "title": "Synthesize a grounded answer",
                    "outcome": "ok",
                    "summary": "wrote",
                    "output": {
                        "synthesized_answer": "Marriage was a contract [ref_1].",
                        "grounded_citations": [
                            {
                                "citation_id": "ref_1",
                                "slice_id": "slice_1",
                                "slice_label": "19th century",
                                "dataset_id": "d84d1a2e-127d-4393-91d0-afb7e4fd9c68",
                                "text_snippet": "Coverture bound a wife to her husband.",
                                "used_in_answer": True,
                            }
                        ],
                    },
                }
            ],
            "synthesized_answer": "Marriage was a contract [ref_1].",
            "grounded_citations": [
                {
                    "citation_id": "ref_1",
                    "slice_id": "slice_1",
                    "slice_label": "19th century",
                    "dataset_id": "d84d1a2e-127d-4393-91d0-afb7e4fd9c68",
                    "text_snippet": "Coverture bound a wife to her husband.",
                    "used_in_answer": True,
                }
            ],
        }
    )
    assert 'data-ref="ref_1"' in markup
    assert 'href="#cite-ref_1"' in markup
    assert 'id="cite-ref_1"' in markup
    assert "Coverture bound a wife to her husband." in markup
    assert "19th C. Knowledge Project (Britannica)" in markup


def test_tree_markup_separates_unused_citations():
    markup = tree_markup(
        {
            "question": "What is the definition of a marriage in the present?",
            "status": "ok",
            "pipeline": [
                {
                    "step": 1,
                    "name": "synthesize",
                    "title": "Synthesize a grounded answer",
                    "outcome": "ok",
                    "summary": "wrote",
                    "output": {},
                }
            ],
            "synthesized_answer": "Today marriage is a civil contract [ref_1] [ref_3].",
            "grounded_citations": [
                {
                    "citation_id": "ref_1",
                    "text_snippet": "used one",
                    "used_in_answer": True,
                    "dataset_id": "1f6fba0c-9aea-4345-b5a3-457c924f9e0c",
                },
                {
                    "citation_id": "ref_2",
                    "text_snippet": "unused hit",
                    "used_in_answer": False,
                    "dataset_id": "1f6fba0c-9aea-4345-b5a3-457c924f9e0c",
                },
                {
                    "citation_id": "ref_3",
                    "text_snippet": "used two",
                    "used_in_answer": True,
                    "dataset_id": "1f6fba0c-9aea-4345-b5a3-457c924f9e0c",
                },
            ],
        }
    )
    assert "2 cited · 1 retrieved" in markup
    assert "Retrieved but not cited" in markup
    assert markup.index("used one") < markup.index("Retrieved but not cited") < markup.index("unused hit")


def test_tree_token_endpoint_returns_access_token(monkeypatch):
    from fastapi.testclient import TestClient
    from src.app.main import app

    monkeypatch.setenv("TREE_AUTO_TOKEN", "true")
    monkeypatch.setattr(
        "src.app.main.cached_oidc_access_token",
        lambda **kwargs: "demo-jwt-token",
    )
    client = TestClient(app)
    response = client.get("/tree/token")
    assert response.status_code == 200
    assert response.json()["access_token"] == "demo-jwt-token"
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["expires_in"] is None


def test_tree_token_refreshes_expired_jwt(monkeypatch):
    import base64
    import json
    import time

    from fastapi.testclient import TestClient
    from src.app.main import app

    def encode(payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"header.{body}.sig"

    expired = encode({"exp": int(time.time()) - 10})
    fresh = encode({"exp": int(time.time()) + 300})
    calls = {"n": 0}

    def fake_cached(*, force: bool = False):
        calls["n"] += 1
        return fresh if force else expired

    monkeypatch.setenv("TREE_AUTO_TOKEN", "true")
    monkeypatch.setattr("src.app.main.cached_oidc_access_token", fake_cached)
    client = TestClient(app)
    response = client.get("/tree/token")
    assert response.status_code == 200
    assert response.json()["access_token"] == fresh
    assert response.json()["expires_in"] is not None
    assert response.json()["expires_in"] > 0
    assert calls["n"] == 2


def test_tree_questions_lists_benchmark_rows():
    from fastapi.testclient import TestClient
    from src.app.main import app

    client = TestClient(app)
    response = client.get("/tree/questions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 1
    questions = body["questions"]
    marriage = next(item for item in questions if item["query_id"] == "9")
    assert "marriage" in marriage["question"].lower()
    assert marriage["concept"]
