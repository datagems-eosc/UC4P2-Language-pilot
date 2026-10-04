import json
from urllib.request import Request

from src.oidc import fetch_oidc_access_token, reset_oidc_cache


def test_fetch_oidc_access_token(monkeypatch):
    reset_oidc_cache()
    captured = {}

    def fake_urlopen(request: Request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")

        class _Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"access_token": "jwt-from-keycloak", "expires_in": 300}).encode()

        return _Response()

    monkeypatch.setattr("src.oidc.urllib.request.urlopen", fake_urlopen)
    token = fetch_oidc_access_token(
        username="dg-user-1",
        password="secret",
        token_url="https://example/token",
        client_id="swagger-client",
        scope="openid",
    )
    assert token == "jwt-from-keycloak"
    assert captured["url"] == "https://example/token"
    assert "grant_type=password" in captured["body"]
    assert "username=dg-user-1" in captured["body"]
