"""OIDC Bearer token validation for protected API endpoints."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "").lower() in {"1", "true", "yes"}


def _issuer_url() -> Optional[str]:
    issuer = os.getenv("OIDC_ISSUER_URL", "").strip()
    return issuer or None


def _audience() -> Optional[str]:
    audience = os.getenv("OIDC_AUDIENCE", "").strip()
    return audience or None


def auth_required() -> bool:
    if _auth_disabled():
        return False
    if os.getenv("AUTH_REQUIRED", "").lower() in {"1", "true", "yes"}:
        return True
    return _issuer_url() is not None


@lru_cache()
def _jwks_client(issuer: str):
    from jwt import PyJWKClient

    jwks_url = f"{issuer.rstrip('/')}/protocol/openid-connect/certs"
    return PyJWKClient(jwks_url)


def _audience_matches(payload: Dict[str, Any], audience: str) -> bool:
    aud = payload.get("aud")
    if isinstance(aud, str) and aud == audience:
        return True
    if isinstance(aud, list) and audience in aud:
        return True
    return payload.get("azp") == audience


def verify_access_token(token: str) -> Dict[str, Any]:
    issuer = _issuer_url()
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC_ISSUER_URL is not configured.",
        )
    try:
        from jwt import PyJWTError, decode as jwt_decode

        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        payload = jwt_decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_aud": False},
        )
    except PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    audience = _audience()
    if audience and not _audience_matches(payload, audience):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token: audience mismatch.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def require_access_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Dict[str, Any]:
    if not auth_required():
        return {}
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return verify_access_token(credentials.credentials)
