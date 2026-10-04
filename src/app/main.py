"""FastAPI service for the UC4P2 language-pilot pipeline."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.app.auth import require_access_token
from src.app.runner import PIPELINE_STEPS, run_compare
from src.app.schemas import QueryRequest, ThematicExplorationRequest, ThematicExplorationResponse
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
        "POST /compare is kept as an alias."
    ),
    version="0.1.5",
    openapi_url="/openapi.json",
    docs_url="/swagger",
    redoc_url="/redoc",
    lifespan=lifespan,
    default_response_class=PrettyJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "UC4P2 Language Pilot",
        "version": "0.1.5",
        "docs": "/swagger",
        "thematic_exploration": "POST /ThematicExploration",
        "compare": "POST /compare (alias)",
        "steps": [item["path"] for item in PIPELINE_STEPS],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


def _run_pipeline(body: QueryRequest, until: str | None = None) -> ThematicExplorationResponse:
    try:
        payload = run_compare(
            body.query,
            query_id=body.query_id,
            until=until,
            include_trace=body.include_trace,
            k=body.k or 5,
        )
    except Exception as exc:
        logger.exception("pipeline failed until=%s", until)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload["service"] = "UC4P2 Language Pilot"
    payload["question"] = body.query
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
