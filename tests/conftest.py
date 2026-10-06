"""Keep unit tests off the GPU checkpoint and off a live language model."""

import pytest


@pytest.fixture(autouse=True)
def offline_qdmr(monkeypatch):
    monkeypatch.setenv("QDMR_BACKEND", "dspy")
    monkeypatch.setenv("QDMR_MODEL_NAME_OR_PATH", "")
    monkeypatch.setenv("QDMR_MOCK", "false")
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.setenv("JUDGE_DISABLED", "true")
