"""FastAPI service for the UC4P2 language-pilot pipeline."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.app.auth import require_access_token
from src.app.runner import run_compare
from src.app.schemas import CompareRequest, CompareResponse
from src.llm import configure_lm_from_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured = configure_lm_from_env()
    logger.info("LLM configured: %s", configured)
    yield


app = FastAPI(
    title="UC4P2 Language Pilot",
    description=(
        "Historical comparative QA: disambiguate, decompose, retrieve from "
        "Cross-Dataset Discovery, and synthesize a grounded answer."
    ),
    version="0.1.0",
    openapi_url="/openapi.json",
    docs_url="/swagger",
    redoc_url="/redoc",
    lifespan=lifespan,
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
        "version": "0.1.0",
        "docs": "/swagger",
        "compare": "POST /compare",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post(
    "/compare",
    response_model=CompareResponse,
    summary="Run the comparative language-pilot pipeline",
    tags=["Pilot"],
)
async def compare(
    body: CompareRequest,
    _: dict[str, Any] = Depends(require_access_token),
) -> CompareResponse:
    """Disambiguate, retrieve one Cross-Dataset Discovery search per slice, and answer."""
    try:
        payload = run_compare(
            body.query,
            query_id=body.query_id,
            until=body.until,
            include_trace=body.include_trace,
            k=body.k or 5,
        )
    except Exception as exc:
        logger.exception("compare failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    payload["service"] = "UC4P2 Language Pilot"
    payload["question"] = body.query
    return CompareResponse.model_validate(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
    )
