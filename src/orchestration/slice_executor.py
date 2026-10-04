"""Per-step retrieval against the Cross-Dataset Discovery API.

``SliceExecutor`` is the DSPy signature for an analytical step. Passage text
itself is taken from the search API and is not rewritten by the model.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

import dspy
from pydantic import BaseModel, Field

from src.oidc import OIDCTokenError, bearer_token_from_env, cached_oidc_access_token, reset_oidc_cache

DEFAULT_DISCOVERY_URL = "https://datagems-dev.scayle.es/cross-dataset-discovery"


class RetrievalAPIError(RuntimeError):
    """Cross-Dataset Discovery could not be called."""


class SliceExecutor(dspy.Signature):
    """Execute one comparative sub-task and return structured citations."""

    step_instruction: str = dspy.InputField()
    slice_label: str = dspy.InputField()
    facets: str = dspy.InputField()
    passages_json: str = dspy.OutputField(
        desc="JSON list of citations with passage_id, text, and metadata"
    )


class Citation(BaseModel):
    passage_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    slice_id: str
    source_corpus: str


class CrossDatasetDiscoveryClient:
    """Client for ``POST /search/`` on Cross-Dataset Discovery.

    See https://datagems-eosc.github.io/cross-dataset-discovery-docs/latest/api-overview/
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 60.0,
        search_mode: str | None = None,
    ):
        configured = base_url or os.getenv(
            "CROSS_DATASET_DISCOVERY_URL", DEFAULT_DISCOVERY_URL
        )
        self.base_url = configured.rstrip("/")
        if token is not None:
            self.token = token
        else:
            try:
                self.token = bearer_token_from_env(os.getenv("CROSS_DATASET_DISCOVERY_TOKEN"))
            except OIDCTokenError:
                self.token = os.getenv("CROSS_DATASET_DISCOVERY_TOKEN")
        self.timeout = timeout
        self.search_mode = search_mode or os.getenv("CROSS_DATASET_SEARCH_MODE", "hybrid")
        self._refresh_on_unauthorized = token is None and not os.getenv("CROSS_DATASET_DISCOVERY_TOKEN")

    def search(
        self,
        query: str,
        k: int = 5,
        dataset_ids: list[str] | None = None,
        search_mode: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/search/"
        ids = dataset_ids if dataset_ids is not None else _dataset_ids_from_env()
        # API rejects dataset_ids=[] — omit the field to search all corpora.
        body: dict[str, Any] = {
            "query": query,
            "k": k,
            "search_mode": search_mode or self.search_mode,
        }
        if ids:
            body["dataset_ids"] = ids
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
            method="POST",
        )
        try:
            payload = self._post(request)
        except urllib.error.HTTPError as exc:
            if exc.code == 401 and self._try_refresh_token():
                request = urllib.request.Request(
                    url,
                    data=request.data,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Authorization": f"Bearer {self.token}",
                    },
                    method="POST",
                )
                try:
                    payload = self._post(request)
                except urllib.error.HTTPError as retry_exc:
                    detail = retry_exc.read().decode("utf-8", errors="replace")
                    raise RetrievalAPIError(
                        f"Cross-Dataset Discovery returned HTTP {retry_exc.code}: {detail}"
                    ) from retry_exc
            else:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RetrievalAPIError(
                    f"Cross-Dataset Discovery returned HTTP {exc.code}: {detail}"
                ) from exc
        except urllib.error.URLError as exc:
            raise RetrievalAPIError(
                f"Cross-Dataset Discovery is unreachable: {exc.reason}"
            ) from exc
        if not isinstance(payload, dict):
            raise RetrievalAPIError("Cross-Dataset Discovery returned a non-object payload.")
        return payload

    def _post(self, request: urllib.request.Request) -> dict[str, Any]:
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _try_refresh_token(self) -> bool:
        if not self._refresh_on_unauthorized:
            return False
        try:
            reset_oidc_cache()
            self.token = cached_oidc_access_token(force=True)
        except OIDCTokenError:
            return False
        return bool(self.token)


def _dataset_ids_from_env() -> list[str]:
    raw = os.getenv("CROSS_DATASET_IDS", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def citations_from_search(payload: dict[str, Any], slice_id: str) -> list[Citation]:
    """Map a search response onto grounded citations."""
    citations: list[Citation] = []
    for item in payload.get("results") or []:
        if not isinstance(item, dict):
            continue
        dataset_id = str(item.get("dataset_id") or "")
        citations.append(
            Citation(
                passage_id=str(item.get("object_id") or ""),
                text=str(item.get("content") or ""),
                metadata={
                    "dataset_id": dataset_id,
                    "similarity": item.get("similarity"),
                    "slice": slice_id,
                    "source_corpus": dataset_id or "cross-dataset-discovery",
                },
                slice_id=slice_id,
                source_corpus=dataset_id or "cross-dataset-discovery",
            )
        )
    return citations


def build_search_query(
    concept: str,
    slice_label: str,
    facets: list[str],
    cross_lingual_tokens: list[str],
) -> str:
    parts = [concept, slice_label, *facets[:6], *cross_lingual_tokens[:4]]
    return " ".join(part for part in parts if part).strip()


class SliceExecutionEngine:
    """Run retrieve steps against Cross-Dataset Discovery."""

    def __init__(self, client: CrossDatasetDiscoveryClient | None = None, k: int = 5):
        self.client = client or CrossDatasetDiscoveryClient()
        self.k = k

    def retrieve(
        self,
        *,
        concept: str,
        slice_id: str,
        slice_label: str,
        facets: list[str],
        cross_lingual_tokens: list[str],
        dataset_ids: list[str] | None = None,
    ) -> list[Citation]:
        query = build_search_query(concept, slice_label, facets, cross_lingual_tokens)
        payload = self.client.search(query, k=self.k, dataset_ids=dataset_ids)
        return citations_from_search(payload, slice_id)
