"""Runtime settings for the Pilot 2 pipeline."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

BREAK_QDMR_MODEL = "mrm8488/t5-base-finetuned-break_data"


class Settings(BaseSettings):
    """QDMR backend selection.

    The default decomposer drafts with the Break checkpoint, then rewrites
    that draft with DSPy so the sub-questions match the benchmark few-shots.
    ``QDMR_BACKEND=finetuned`` skips the rewrite. ``QDMR_BACKEND=dspy`` skips
    the Break draft. ``QDMR_BACKEND=dspy_advanced`` uses the multi-stage
    ChainOfThought planner with assertion repair and optional MIPROv2 weights.
    ``QDMR_MOCK=true`` forces the headless plan.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qdmr_backend: str = "refined"
    qdmr_model_name_or_path: str = BREAK_QDMR_MODEL
    qdmr_mock: bool = False
    qdmr_compiled_path: str = "artifacts/compiled_qdmr.json"
    # Chat endpoint: scayle, ollama, openai, or gemini. Read by src/llm.py.
    llm_provider: str = "scayle"


def get_settings() -> Settings:
    """Read the current environment. Not cached, so tests can change it."""
    return Settings()
