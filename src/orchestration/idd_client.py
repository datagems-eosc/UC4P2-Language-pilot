"""HTTP client for in-dataset-discovery question tools (decompose / extend / NLG)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from src.oidc import OIDCTokenError, bearer_token_from_env

DEFAULT_IDD_URL = "https://datagems-dev.scayle.es/in-dataset-discovery"


class InDatasetDiscoveryError(RuntimeError):
    """The in-dataset-discovery service could not be called."""


def use_in_dataset_discovery() -> bool:
    """True when the pilot should call IDD for extend / decompose / NLG."""
    raw = (os.getenv("USE_IN_DATASET_DISCOVERY") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    # Default on when a URL is explicitly configured.
    return bool((os.getenv("IN_DATASET_DISCOVERY_URL") or "").strip())


def _post_json(url: str, payload: dict[str, Any], token: str | None, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise InDatasetDiscoveryError(
            f"in-dataset-discovery returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise InDatasetDiscoveryError(
            f"in-dataset-discovery is unreachable: {exc.reason}"
        ) from exc
    if not isinstance(body, dict):
        raise InDatasetDiscoveryError("in-dataset-discovery returned a non-object payload.")
    return body


class InDatasetDiscoveryClient:
    """Client for IDD ``/decompose``, ``/extendKnowledge``, ``/nlgEvaluate``."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 120.0,
    ):
        configured = base_url or os.getenv("IN_DATASET_DISCOVERY_URL", DEFAULT_IDD_URL)
        self.base_url = configured.rstrip("/")
        if token is not None:
            self.token = token
        else:
            try:
                self.token = bearer_token_from_env(
                    os.getenv("IN_DATASET_DISCOVERY_TOKEN")
                    or os.getenv("CROSS_DATASET_DISCOVERY_TOKEN")
                )
            except OIDCTokenError:
                self.token = os.getenv("IN_DATASET_DISCOVERY_TOKEN") or os.getenv(
                    "CROSS_DATASET_DISCOVERY_TOKEN"
                )
        self.timeout = timeout

    def decompose(
        self,
        question: str,
        *,
        concept: str | None = None,
        slices: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"question": question}
        if concept:
            payload["concept"] = concept
        if slices:
            payload["slices"] = slices
        return _post_json(
            f"{self.base_url}/decompose", payload, self.token, self.timeout
        )

    def extend_knowledge(
        self,
        question: str,
        *,
        concept: str | None = None,
        slices: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"question": question}
        if concept:
            payload["concept"] = concept
        if slices:
            payload["slices"] = slices
        return _post_json(
            f"{self.base_url}/extendKnowledge", payload, self.token, self.timeout
        )

    def nlg_evaluate(
        self,
        question: str,
        answer: str,
        *,
        query_id: str | None = None,
        ground_truth: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"question": question, "answer": answer}
        if query_id:
            payload["query_id"] = query_id
        if ground_truth:
            payload["ground_truth"] = ground_truth
        return _post_json(
            f"{self.base_url}/nlgEvaluate", payload, self.token, self.timeout
        )
