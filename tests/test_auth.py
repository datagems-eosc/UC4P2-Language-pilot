from fastapi.testclient import TestClient

from src.app.auth import auth_required, require_access_token
from src.app.main import app


def test_auth_required_when_oidc_configured(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://example.com/realms/dev")
    from src.app import auth

    auth._jwks_client.cache_clear()
    try:
        assert auth_required() is True
    finally:
        auth._jwks_client.cache_clear()


def test_auth_disabled_for_local_tests(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.delenv("OIDC_ISSUER_URL", raising=False)
    from src.app import auth

    assert auth_required() is False


def test_audience_matches_azp_when_aud_list_does_not_include_client():
    from src.app.auth import _audience_matches

    payload = {
        "aud": ["account"],
        "azp": "swagger-client",
    }
    assert _audience_matches(payload, "swagger-client") is True
    assert _audience_matches(payload, "language-pilot") is False


def test_thematic_exploration_returns_401_without_token(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://example.com/realms/dev")
    client = TestClient(app)
    response = client.post(
        "/ThematicExploration",
        json={"query": "How did a marriage look like in the 1800s compared to now?"},
    )
    assert response.status_code == 401
    assert "Bearer" in response.json()["detail"]


def test_health_stays_public_when_auth_required(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://example.com/realms/dev")
    client = TestClient(app)
    assert client.get("/health").status_code == 200


def test_thematic_exploration_accepts_overridden_token(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://example.com/realms/dev")
    app.dependency_overrides[require_access_token] = lambda: {"sub": "test-user"}
    try:
        client = TestClient(app)
        response = client.post(
            "/ThematicExploration",
            headers={"Authorization": "Bearer test-token"},
            json={"query": "How did a marriage look like in the 1800s compared to now?"},
        )
        assert response.status_code != 401
    finally:
        app.dependency_overrides.clear()
