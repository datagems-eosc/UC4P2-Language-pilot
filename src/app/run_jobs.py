"""In-memory ThematicExploration jobs so SSE can drop without losing the run."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}
_MAX_JOBS = 64
_TTL_SECONDS = 3600.0


def put_job(job_id: str, payload: dict[str, Any]) -> None:
    record = {"updated": time.time(), "payload": payload}
    with _LOCK:
        _JOBS[job_id] = record
        _prune_locked()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        record = _JOBS.get(job_id)
        if record is None:
            return None
        return record["payload"]


def _prune_locked() -> None:
    cutoff = time.time() - _TTL_SECONDS
    stale = [key for key, record in _JOBS.items() if record["updated"] < cutoff]
    for key in stale:
        _JOBS.pop(key, None)
    if len(_JOBS) <= _MAX_JOBS:
        return
    oldest = sorted(_JOBS.items(), key=lambda item: item[1]["updated"])
    for key, _ in oldest[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(key, None)
