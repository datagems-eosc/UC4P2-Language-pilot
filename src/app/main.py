"""FastAPI service for the UC4P2 language-pilot pipeline."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from src.app.auth import caller_access_token, require_access_token
from src.app.run_jobs import get_job, put_job
from src.app.run_memory import (
    attach_memory_meta,
    load_run,
    memory_enabled,
    memory_key,
    save_run,
    should_store,
)
from src.app.runner import PIPELINE_STEPS, iter_compare, run_compare
from src.app.schemas import QueryRequest, ThematicExplorationRequest, ThematicExplorationResponse
from src.app.tree import html_response
from src.evaluation.nlg import list_data_questions
from src.llm import configure_lm_from_env
from src.oidc import OIDCTokenError, cached_oidc_access_token, fetch_oidc_access_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class PrettyJSONResponse(JSONResponse):
    """Indented JSON so curl, Swagger, and browsers show a readable tree."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            default=str,
        ).encode("utf-8")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured = configure_lm_from_env()
    logger.info("LLM configured: %s", configured)
    yield


app = FastAPI(
    title="UC4P2 Language Pilot",
    description=(
        "Historical comparative QA: disambiguate, decompose, retrieve from "
        "Cross-Dataset Discovery, and synthesize a grounded answer. "
        "POST /ThematicExploration runs the full pipeline. POST /steps/<name> stops after that "
        "node and returns it as result, plus pipeline[] for everything up to there. "
        "POST /compare is kept as an alias. "
        "POST /ThematicExploration/stream sends each finished step as SSE. "
        "Protected routes require a DataGEMS AAI Bearer JWT "
        "(Authorization: Bearer <token>), as in dg-app-api. "
        "GET /health is public."
    ),
    version="0.1.26",
    openapi_url="/openapi.json",
    docs_url="/swagger",
    redoc_url="/redoc",
    lifespan=lifespan,
    default_response_class=PrettyJSONResponse,
    swagger_ui_init_oauth={
        "clientId": os.getenv("OIDC_CLIENT_ID", "swagger-client"),
        "appName": "UC4P2 Language Pilot",
        "scopes": os.getenv("OIDC_SCOPE", "openid datagems offline_access"),
        "usePkceWithAuthorizationCodeGrant": False,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Run-Id", "X-Accel-Buffering"],
)


def _token_url() -> str:
    return os.getenv(
        "OIDC_TOKEN_URL",
        "https://datagems-dev.scayle.es/oauth/realms/dev/protocol/openid-connect/token",
    )


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "DataGEMS AAI access token. Same contract as dg-app-api: "
                "Authorization: Bearer <jwt>."
            ),
        },
        "oauth2": {
            "type": "oauth2",
            "flows": {
                "password": {
                    "tokenUrl": _token_url(),
                    "scopes": {
                        "openid": "OpenID",
                        "datagems": "DataGEMS APIs",
                        "offline_access": "Refresh token",
                    },
                }
            },
        },
    }
    protected = {
        "/ThematicExploration",
        "/ThematicExploration/stream",
        "/ThematicExploration/runs/{job_id}",
        "/compare",
        "/tree",
        "/steps/route",
        "/steps/disambiguate",
        "/steps/extend-knowledge",
        "/steps/generate-subquestions",
        "/steps/decompose",
        "/steps/retrieve",
        "/steps/features",
        "/steps/synthesize",
        "/steps/evaluate",
        "/steps/export",
    }
    for path, methods in (schema.get("paths") or {}).items():
        if path not in protected:
            continue
        for operation in methods.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}, {"oauth2": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "UC4P2 Language Pilot",
        "version": "0.1.26",
        "docs": "/swagger",
        "thematic_exploration": "POST /ThematicExploration",
        "thematic_exploration_stream": "POST /ThematicExploration/stream",
        "thematic_exploration_run": "GET /ThematicExploration/runs/{job_id}",
        "tree": "GET /tree",
        "tree_token": "GET /tree/token",
        "tree_questions": "GET /tree/questions",
        "compare": "POST /compare (alias)",
        "steps": [item["path"] for item in PIPELINE_STEPS],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


def _jwt_exp(token: str) -> float | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        exp = payload.get("exp")
        return float(exp) if isinstance(exp, (int, float)) else None
    except (ValueError, json.JSONDecodeError, OSError):
        return None


def _tree_demo_token(*, force: bool = False) -> str:
    """Token for the tree UI auto-fill (same password-grant as EXAMPLES.md curls)."""
    if os.getenv("TREE_AUTO_TOKEN", "true").strip().lower() in {"0", "false", "no", "off"}:
        raise OIDCTokenError("TREE_AUTO_TOKEN is disabled.")

    def _issue(*, refresh: bool) -> str:
        try:
            return cached_oidc_access_token(force=refresh)
        except OIDCTokenError:
            return fetch_oidc_access_token(
                username=os.getenv("TREE_DEMO_USERNAME", "dg-user-1"),
                password=os.getenv("TREE_DEMO_PASSWORD", "dg-user-1"),
            )

    token = _issue(refresh=force)
    exp = _jwt_exp(token)
    if exp is not None and exp < time.time() + 30:
        token = _issue(refresh=True)
    return token


@app.get(
    "/tree/token",
    summary="Default Bearer token for the tree UI",
    tags=["ThematicExploration"],
)
async def tree_token() -> dict[str, Any]:
    """Public helper so the HTML tree can Run without pasting a token each time."""
    try:
        token = _tree_demo_token()
    except OIDCTokenError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    exp = _jwt_exp(token)
    expires_in = max(0, int(exp - time.time())) if exp is not None else None
    return {"access_token": token, "token_type": "Bearer", "expires_in": expires_in}


@app.get(
    "/tree/questions",
    summary="Benchmark questions for the tree drawer",
    tags=["ThematicExploration"],
)
async def tree_questions() -> dict[str, Any]:
    """Public catalog from ``data/*.json`` so the tree UI can pick a question."""
    questions = list(list_data_questions())
    return {"count": len(questions), "questions": questions}


@app.get("/tree", summary="HTML pipeline tree", tags=["ThematicExploration"], response_class=HTMLResponse)
async def tree_view() -> HTMLResponse:
    """Collapsible HTML tree of a ThematicExploration JSON, first pipeline step to last."""
    return html_response()


@app.post("/tree", summary="Render JSON as an HTML tree", tags=["ThematicExploration"], response_class=HTMLResponse)
async def tree_from_json(
    payload: dict[str, Any],
    _: dict[str, Any] = Depends(require_access_token),
) -> HTMLResponse:
    """POST a saved ThematicExploration JSON and get the same tree as GET /tree."""
    return html_response(payload)


def _request_meta(body: QueryRequest, until: str | None) -> dict[str, Any]:
    k = body.k or 5
    return {
        "key": memory_key(
            body.query,
            query_id=body.query_id,
            k=k,
            decompose_mode=body.decompose_mode,
            until=until,
            use_extension_questions=bool(body.use_extension_questions),
        ),
        "k": k,
        "request": {
            "query": body.query,
            "query_id": body.query_id,
            "k": k,
            "decompose_mode": body.decompose_mode,
            "until": until,
            "include_trace": body.include_trace,
            "use_extension_questions": bool(body.use_extension_questions),
        },
        "use_memory": bool(getattr(body, "use_memory", True)) and memory_enabled(),
        "refresh": bool(getattr(body, "refresh", False)),
    }


def _decorate_payload(payload: dict[str, Any], body: QueryRequest) -> dict[str, Any]:
    payload = dict(payload)
    payload["service"] = "UC4P2 Language Pilot"
    payload["question"] = body.query
    return payload


def _cached_payload(body: QueryRequest, until: str | None) -> dict[str, Any] | None:
    meta = _request_meta(body, until)
    if not meta["use_memory"] or meta["refresh"]:
        return None
    cached = load_run(meta["key"])
    if cached is None:
        return None
    payload = _decorate_payload(dict(cached["result"]), body)
    payload = attach_memory_meta(
        payload,
        hit=True,
        key=str(cached.get("key") or meta["key"]),
        stored_at=cached.get("stored_at") if isinstance(cached.get("stored_at"), str) else None,
        path=cached.get("path") if isinstance(cached.get("path"), str) else None,
    )
    logger.info("run memory hit key=%s until=%s", meta["key"][:12], until)
    return payload


def _finalize_payload(payload: dict[str, Any], body: QueryRequest, until: str | None) -> dict[str, Any]:
    meta = _request_meta(body, until)
    payload = _decorate_payload(payload, body)
    if payload.get("status") in {"timeout", "error"}:
        logger.warning(
            "pipeline stopped status=%s failed_step=%s until=%s error=%s",
            payload.get("status"),
            payload.get("failed_step"),
            until,
            payload.get("error"),
        )
    if meta["use_memory"] and should_store(payload):
        stored = save_run(meta["key"], payload, request=meta["request"])
        return attach_memory_meta(
            payload,
            hit=False,
            key=str(stored["key"]),
            stored_at=str(stored.get("stored_at") or ""),
            path=str(stored.get("path") or ""),
        )
    if meta["refresh"] or not meta["use_memory"]:
        return attach_memory_meta(payload, hit=False, key=meta["key"])
    return payload


def _run_pipeline(body: QueryRequest, until: str | None = None) -> ThematicExplorationResponse:
    # run_compare catches step failures and returns intermediate pipeline[] + failed_step
    # instead of a bare {"detail": "..."}. Soft-failed CDD corpus-analysis stays in-band.
    cached = _cached_payload(body, until)
    if cached is not None:
        return ThematicExplorationResponse.model_validate(cached)
    payload = run_compare(
        body.query,
        query_id=body.query_id,
        until=until,
        include_trace=body.include_trace,
        k=body.k or 5,
        decompose_mode=body.decompose_mode,
        use_extension_questions=bool(body.use_extension_questions),
    )
    return ThematicExplorationResponse.model_validate(_finalize_payload(payload, body, until))


def _sse(event: str, payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _slim_running_payload(payload: dict[str, Any], *, limit: int = 240) -> dict[str, Any]:
    """Keep live SSE frames small so HTTP/2 does not reset after retrieve."""

    def slim(value: Any, depth: int = 0) -> Any:
        if depth > 8:
            return value
        if isinstance(value, str) and len(value) > limit:
            return value[:limit] + "…"
        if isinstance(value, list):
            return [slim(item, depth + 1) for item in value[:8]]
        if isinstance(value, dict):
            return {key: slim(item, depth + 1) for key, item in value.items()}
        return value

    slimmed = slim(payload)
    if isinstance(slimmed, dict):
        slimmed["job_id"] = payload.get("job_id")
        slimmed["status"] = payload.get("status") or "running"
    return slimmed if isinstance(slimmed, dict) else dict(payload)


def _stream_pipeline(body: QueryRequest, until: str | None, access_token: str | None):
    cached = _cached_payload(body, until)
    if cached is not None:
        yield cached
        return
    last: dict[str, Any] | None = None
    for payload in iter_compare(
        body.query,
        query_id=body.query_id,
        until=until,
        include_trace=body.include_trace,
        k=body.k or 5,
        decompose_mode=body.decompose_mode,
        use_extension_questions=bool(body.use_extension_questions),
        access_token=access_token,
    ):
        payload = _decorate_payload(payload, body)
        last = payload
        if payload.get("status") == "running":
            yield payload
    if last is not None:
        yield _finalize_payload(last, body, until)


def _start_stream_job(
    body: QueryRequest,
    until: str | None,
    access_token: str | None,
) -> tuple[str, queue.Queue]:
    job_id = uuid.uuid4().hex
    updates: queue.Queue = queue.Queue()
    put_job(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "question": body.query,
            "query_id": body.query_id or "",
            "pipeline": [],
        },
    )

    def worker() -> None:
        try:
            for payload in _stream_pipeline(body, until, access_token):
                payload = dict(payload)
                payload["job_id"] = job_id
                put_job(job_id, payload)
                updates.put(payload)
        except Exception as exc:  # noqa: BLE001 - last snapshot must stay pollable
            logger.exception("stream job failed id=%s", job_id)
            previous = get_job(job_id) or {}
            payload = {
                "job_id": job_id,
                "status": "error",
                "error": str(exc),
                "question": body.query,
                "query_id": body.query_id or "",
                "pipeline": previous.get("pipeline") or [],
                "failed_step": previous.get("last_step") or previous.get("failed_step"),
            }
            put_job(job_id, payload)
            updates.put(payload)
        finally:
            updates.put(None)

    threading.Thread(target=worker, name=f"te-job-{job_id[:8]}", daemon=True).start()
    return job_id, updates


@app.get("/steps", summary="List pipeline step APIs", tags=["Steps"])
async def list_steps() -> dict[str, Any]:
    return {
        "steps": [
            {
                "step": index,
                "name": item["name"],
                "path": f"POST {item['path']}",
                "title": item["title"],
                "summary": item["summary"],
            }
            for index, item in enumerate(PIPELINE_STEPS, start=1)
        ]
    }


@app.post(
    "/ThematicExploration",
    response_model=ThematicExplorationResponse,
    summary="ThematicExploration",
    operation_id="ThematicExploration",
    tags=["ThematicExploration"],
)
@app.post(
    "/compare",
    response_model=ThematicExplorationResponse,
    summary="ThematicExploration (alias)",
    operation_id="compare",
    tags=["ThematicExploration"],
    deprecated=True,
)
async def thematic_exploration(
    body: ThematicExplorationRequest,
    _: dict[str, Any] = Depends(require_access_token),
) -> ThematicExplorationResponse:
    """Run the full thematic-exploration pipeline (or stop at `until`)."""
    return _run_pipeline(body, until=body.until)


@app.post(
    "/ThematicExploration/stream",
    summary="ThematicExploration (SSE stream)",
    operation_id="ThematicExplorationStream",
    tags=["ThematicExploration"],
)
async def thematic_exploration_stream(
    body: ThematicExplorationRequest,
    _: dict[str, Any] = Depends(require_access_token),
) -> StreamingResponse:
    """Stream each finished pipeline step as Server-Sent Events.

    `event: step` payloads have `status=running` and a growing `pipeline[]`.
    The last `event: done` is the same document as POST /ThematicExploration.
    The pipeline keeps running in a background job if the SSE connection drops;
    poll GET /ThematicExploration/runs/{job_id} for the latest snapshot.
    """
    token = caller_access_token()
    job_id, updates = _start_stream_job(body, body.until, token)

    async def generate():
        yield f": job {job_id}\n\n".encode("utf-8")
        yield _sse("job", {"job_id": job_id, "status": "running"})
        while True:
            try:
                item = await asyncio.to_thread(updates.get, True, 1.0)
            except queue.Empty:
                yield b": keepalive\n\n"
                continue
            if item is None:
                break
            event = "done" if item.get("status") != "running" else "step"
            frame = item if event == "done" else _slim_running_payload(item)
            yield _sse(event, frame)
            if event == "done":
                break
            yield b": keepalive\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Run-Id": job_id,
        },
    )


@app.get(
    "/ThematicExploration/runs/{job_id}",
    summary="ThematicExploration run snapshot",
    tags=["ThematicExploration"],
)
async def thematic_exploration_run(
    job_id: str,
    _: dict[str, Any] = Depends(require_access_token),
) -> dict[str, Any]:
    """Latest snapshot of a streamed run, including after the SSE connection drops."""
    payload = get_job(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Unknown or expired run.")
    return payload


def _register_step(spec: dict[str, str]) -> None:
    until = spec["name"]

    async def handler(
        body: QueryRequest,
        _: dict[str, Any] = Depends(require_access_token),
    ) -> ThematicExplorationResponse:
        return _run_pipeline(body, until=until)

    handler.__name__ = f"step_{until}"
    handler.__doc__ = spec["summary"]
    app.add_api_route(
        spec["path"],
        handler,
        methods=["POST"],
        response_model=ThematicExplorationResponse,
        summary=spec["title"],
        description=(
            f"{spec['summary']} Runs every node up to `{until}` and returns that "
            "node as `result`, with the prefix in `pipeline`."
        ),
        tags=["Steps"],
    )


for _spec in PIPELINE_STEPS:
    _register_step(_spec)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
    )
