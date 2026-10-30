"""Persistent memory for ThematicExploration runs.

Same question (+ options) returns the stored pipeline result instead of
re-running. Pass ``refresh=true`` (or ``use_memory=false``) to force a new run
and check consistency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


def memory_root() -> Path:
    configured = (os.getenv("RUN_MEMORY_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path(__file__).resolve().parents[2] / "runs" / "memory"


def normalize_question(question: str) -> str:
    return _WS.sub(" ", (question or "").strip().casefold())


def memory_key(
    question: str,
    *,
    query_id: str | None,
    k: int,
    decompose_mode: str,
    until: str | None,
    use_extension_questions: bool = False,
    llm_model: str | None = None,
    judge_llm_model: str | None = None,
) -> str:
    payload = {
        "question": normalize_question(question),
        "query_id": (query_id or "").strip(),
        "k": int(k),
        "decompose_mode": (decompose_mode or "").strip().lower(),
        "until": (until or "").strip(),
        "use_extension_questions": bool(use_extension_questions),
        "llm_model": (llm_model or "").strip(),
        "judge_llm_model": (judge_llm_model or "").strip(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return digest


def _path_for_key(key: str) -> Path:
    return memory_root() / f"{key}.json"


def memory_enabled() -> bool:
    return os.getenv("RUN_MEMORY_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def load_run(key: str) -> dict[str, Any] | None:
    path = _path_for_key(key)
    if not path.is_file():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("run memory unreadable key=%s err=%s", key, exc)
        return None
    if not isinstance(envelope, dict):
        return None
    result = envelope.get("result")
    if not isinstance(result, dict):
        return None
    return {
        "result": result,
        "stored_at": envelope.get("stored_at"),
        "key": envelope.get("key") or key,
        "path": str(path),
        "request": envelope.get("request") or {},
    }


def save_run(
    key: str,
    result: dict[str, Any],
    *,
    request: dict[str, Any],
) -> dict[str, Any]:
    root = memory_root()
    root.mkdir(parents=True, exist_ok=True)
    path = _path_for_key(key)
    stored_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    envelope = {
        "key": key,
        "stored_at": stored_at,
        "request": request,
        "result": result,
    }
    # Atomic replace so readers never see a partial file.
    fd, tmp_name = tempfile.mkstemp(prefix=f".{key}.", suffix=".json", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(envelope, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        Path(tmp_name).replace(path)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return {"key": key, "stored_at": stored_at, "path": str(path), "hit": False}


def should_store(result: dict[str, Any]) -> bool:
    """Cache completed and clarification runs; skip hard failures."""
    status = str(result.get("status") or "")
    return status in {"ok", "clarification", "partial"}


def attach_memory_meta(
    result: dict[str, Any],
    *,
    hit: bool,
    key: str,
    stored_at: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    result = dict(result)
    result["memory"] = {
        "hit": hit,
        "key": key,
        "stored_at": stored_at,
        "path": path,
    }
    return result
