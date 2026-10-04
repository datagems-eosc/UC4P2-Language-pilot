import pytest

from src.config import Settings
from src.decomposition.advanced_dspy_module import AdvancedQDMRDecomposer
from src.decomposition.backends.dspy_backend import DSPyQDMRBackend
from src.decomposition.backends.finetuned_backend import FineTunedQDMRBackend
from src.decomposition.factory import QDMRDecomposerFactory


def test_factory_reads_backend_from_environment(monkeypatch):
    monkeypatch.setenv("QDMR_BACKEND", "finetuned")
    monkeypatch.setenv("QDMR_MODEL_NAME_OR_PATH", "")
    created = QDMRDecomposerFactory.create()
    assert isinstance(created, FineTunedQDMRBackend)
    assert created.uses_mock is True


def test_default_decomposer_is_break_then_dspy(monkeypatch):
    monkeypatch.delenv("QDMR_BACKEND", raising=False)
    monkeypatch.delenv("QDMR_MODEL_NAME_OR_PATH", raising=False)
    monkeypatch.delenv("QDMR_MOCK", raising=False)
    settings = Settings()
    assert settings.qdmr_backend == "refined"
    assert settings.qdmr_model_name_or_path == "mrm8488/t5-base-finetuned-break_data"


def test_factory_argument_overrides_environment(monkeypatch):
    monkeypatch.setenv("QDMR_BACKEND", "finetuned")
    created = QDMRDecomposerFactory.create(backend="dspy")
    assert isinstance(created, DSPyQDMRBackend)


def test_factory_uses_settings_object():
    settings = Settings(qdmr_backend="dspy", qdmr_model_name_or_path="", qdmr_mock=False)
    assert isinstance(QDMRDecomposerFactory.create(settings=settings), DSPyQDMRBackend)


def test_factory_builds_advanced_dspy_backend(monkeypatch):
    monkeypatch.setenv("QDMR_BACKEND", "dspy_advanced")
    monkeypatch.delenv("QDMR_COMPILED_PATH", raising=False)
    created = QDMRDecomposerFactory.create()
    assert isinstance(created, AdvancedQDMRDecomposer)


def test_factory_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown QDMR backend"):
        QDMRDecomposerFactory.create(backend="pairwise")
