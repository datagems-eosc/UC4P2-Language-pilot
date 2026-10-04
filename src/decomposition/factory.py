"""Select a QDMR backend from an argument, then the environment."""

from __future__ import annotations

from pathlib import Path

from src.config import Settings, get_settings
from src.decomposition.backends.dspy_backend import DSPyQDMRBackend
from src.decomposition.backends.finetuned_backend import FineTunedQDMRBackend
from src.decomposition.backends.refined_backend import RefinedQDMRBackend
from src.decomposition.base import BaseQDMRDecomposer

_DSPY = {"dspy", "prompt"}
_FINETUNED = {"finetuned", "huggingface", "hf"}
_REFINED = {"refined", "break-dspy", "hybrid"}
_ADVANCED = {"dspy_advanced", "advanced", "mipro"}

_DEFAULT_COMPILED = Path(__file__).resolve().parents[2] / "artifacts" / "compiled_qdmr.json"


class QDMRDecomposerFactory:
    """Build the decomposer named by ``backend`` or ``QDMR_BACKEND``."""

    @staticmethod
    def create(
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> BaseQDMRDecomposer:
        cfg = settings or get_settings()
        name = (backend if backend is not None else cfg.qdmr_backend).strip().lower()
        if name in _DSPY:
            return DSPyQDMRBackend()
        if name in _FINETUNED:
            return FineTunedQDMRBackend(
                model_name_or_path=cfg.qdmr_model_name_or_path,
                mock=cfg.qdmr_mock or not cfg.qdmr_model_name_or_path.strip(),
            )
        if name in _REFINED:
            return RefinedQDMRBackend(
                model_name_or_path=cfg.qdmr_model_name_or_path,
                mock=cfg.qdmr_mock or not cfg.qdmr_model_name_or_path.strip(),
            )
        if name in _ADVANCED:
            return QDMRDecomposerFactory._advanced(cfg)
        raise ValueError(
            "Unknown QDMR backend "
            f"{name!r}. Use 'refined', 'finetuned', 'dspy', or 'dspy_advanced'."
        )

    @staticmethod
    def _advanced(cfg: Settings) -> BaseQDMRDecomposer:
        from src.decomposition.advanced_dspy_module import AdvancedQDMRDecomposer
        from src.decomposition.optimizer import load_compiled_decomposer

        path = Path(cfg.qdmr_compiled_path or _DEFAULT_COMPILED)
        if path.is_file():
            try:
                return load_compiled_decomposer(str(path))
            except Exception:
                pass
        return AdvancedQDMRDecomposer()
