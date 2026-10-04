"""Password-grant tokens for DataGEMS Keycloak.

Used by Cross-Dataset Discovery and, when required, query-disambiguation.
Matches the curl template:

    POST .../oauth/realms/dev/protocol/openid-connect/token
    grant_type=password&client_id=swagger-client
    username=...&password=...
    scope=openid cross-dataset-discovery-api offline_access
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

DEFAULT_OIDC_TOKEN_URL = (
    "https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token"
)
DEFAULT_OIDC_CLIENT_ID = "swagger-client"
DEFAULT_OIDC_SCOPE = "openid cross-dataset-discovery-api offline_access"

_lock = threading.Lock()
_cached_token: str | None = None
_cached_until: float = 0.0


class OIDCTokenError(RuntimeError):
    """Keycloak did not issue an access token."""


def _token_url() -> str:
    return (
        os.getenv("OIDC_TOKEN_URL")
        or os.getenv("KEYCLOAK_TOKEN_URL")
        or DEFAULT_OIDC_TOKEN_URL
    ).strip()


def fetch_oidc_access_token(
    *,
    username: str | None = None,
    password: str | None = None,
    token_url: str | None = None,
    client_id: str | None = None,
    scope: str | None = None,
    timeout: float = 30.0,
) -> str:
    """Request a new access token. Does not read the module cache."""
    user = (username or os.getenv("DG_USERNAME") or os.getenv("OIDC_USERNAME") or "").strip()
    secret = (password or os.getenv("DG_PASSWORD") or os.getenv("OIDC_PASSWORD") or "").strip()
    if not user or not secret:
        raise OIDCTokenError(
            "DG_USERNAME and DG_PASSWORD (or OIDC_USERNAME / OIDC_PASSWORD) are required."
        )
    url = (token_url or _token_url()).strip()
    body = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": (client_id or os.getenv("OIDC_CLIENT_ID") or DEFAULT_OIDC_CLIENT_ID).strip(),
            "username": user,
            "password": secret,
            "scope": (scope or os.getenv("OIDC_SCOPE") or DEFAULT_OIDC_SCOPE).strip(),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OIDCTokenError(f"OIDC token endpoint returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise OIDCTokenError(f"OIDC token endpoint is unreachable: {exc.reason}") from exc
    token = payload.get("access_token")
    if not token:
        raise OIDCTokenError("OIDC token endpoint did not return access_token.")
    expires = float(payload.get("expires_in") or 300)
    with _lock:
        global _cached_token, _cached_until
        _cached_token = str(token)
        _cached_until = time.time() + max(30.0, expires - 30.0)
    return str(token)


def cached_oidc_access_token(*, force: bool = False) -> str:
    """Return a cached token, refreshing when it is close to expiry."""
    global _cached_token, _cached_until
    with _lock:
        if not force and _cached_token and time.time() < _cached_until:
            return _cached_token
    return fetch_oidc_access_token()


def reset_oidc_cache() -> None:
    global _cached_token, _cached_until
    with _lock:
        _cached_token = None
        _cached_until = 0.0


def bearer_token_from_env(explicit: Optional[str] = None) -> Optional[str]:
    """Prefer an explicit JWT, then fetch one from Keycloak when credentials exist."""
    if explicit:
        return explicit
    for name in (
        "CROSS_DATASET_DISCOVERY_TOKEN",
        "QUERY_DISAMBIGUATION_TOKEN",
        "DATAGEMS_ACCESS_TOKEN",
    ):
        value = os.getenv(name, "").strip()
        if value:
            return value
    user = (os.getenv("DG_USERNAME") or os.getenv("OIDC_USERNAME") or "").strip()
    secret = (os.getenv("DG_PASSWORD") or os.getenv("OIDC_PASSWORD") or "").strip()
    if not user or not secret:
        return None
    return cached_oidc_access_token()
