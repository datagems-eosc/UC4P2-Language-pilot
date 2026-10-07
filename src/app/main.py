"""FastAPI service for the UC4P2 language-pilot pipeline."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse

from src.app.auth import require_access_token
from src.app.runner import PIPELINE_STEPS, run_compare
from src.app.schemas import QueryRequest, ThematicExplorationRequest, ThematicExplorationResponse
from src.app.tree import html_response
from src.llm import configure_lm_from_env

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
        "Protected routes require a DataGEMS AAI Bearer JWT "
        "(Authorization: Bearer <token>), as in dg-app-api. "
        "GET /health is public."
    ),
    version="0.1.12",
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
        "version": "0.1.12",
        "docs": "/swagger",
        "thematic_exploration": "POST /ThematicExploration",
        "tree": "GET /tree",
        "compare": "POST /compare (alias)",
        "steps": [item["path"] for item in PIPELINE_STEPS],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


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


def _run_pipeline(body: QueryRequest, until: str | None = None) -> ThematicExplorationResponse:
    # run_compare catches step failures and returns intermediate pipeline[] + failed_step
    # instead of a bare {"detail": "..."}. Soft-failed CDD corpus-analysis stays in-band.
    payload = run_compare(
        body.query,
        query_id=body.query_id,
        until=until,
        include_trace=body.include_trace,
        k=body.k or 5,
        decompose_mode=body.decompose_mode,
    )
    payload["service"] = "UC4P2 Language Pilot"
    payload["question"] = body.query
    if payload.get("status") in {"timeout", "error"}:
        logger.warning(
            "pipeline stopped status=%s failed_step=%s until=%s error=%s",
            payload.get("status"),
            payload.get("failed_step"),
            until,
            payload.get("error"),
        )
    return ThematicExplorationResponse.model_validate(payload)


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
