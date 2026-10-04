"""Hugging Face seq2seq backend for Break-style QDMR strings.

When the checkpoint, ``transformers``, or a GPU path is unavailable, generation
falls back to a headless Break string and the shared parser. The returned
steps match the DSPy backend's typed contract.
"""

from __future__ import annotations

from typing import Any

from src.decomposition.base import (
    BaseQDMRDecomposer,
    QDMRStep,
    build_comparative_steps,
    ensure_synthesize_root,
    steps_are_valid,
)
from src.decomposition.refine_utils import normalize_break_steps
from src.decomposition.syntax_parser import parse_decomposition, steps_to_break
from src.schemas.slice import ComparisonSlice


def _allow_old_torchvision() -> None:
    """Transformers 5 expects an enum member missing from older torchvision."""
    try:
        from torchvision.transforms import InterpolationMode
    except Exception:
        return
    if not hasattr(InterpolationMode, "NEAREST_EXACT"):
        InterpolationMode.NEAREST_EXACT = InterpolationMode.NEAREST


def _resolve_checkpoint(name: str) -> str:
    """Prefer a local safetensors snapshot. Torch 2.5 refuses ``pytorch_model.bin``."""
    from pathlib import Path

    path = Path(name)
    if path.is_dir() and (path / "model.safetensors").is_file():
        return str(path)
    if "/" not in name:
        return name
    root = (
        Path.home()
        / ".cache/huggingface/hub"
        / ("models--" + name.replace("/", "--"))
        / "snapshots"
    )
    if not root.is_dir():
        return name
    weights = None
    tokenizer_source = None
    for snapshot in root.iterdir():
        if (snapshot / "model.safetensors").is_file():
            weights = snapshot
        if (snapshot / "spiece.model").is_file():
            tokenizer_source = snapshot
    if weights is None:
        return name
    if tokenizer_source is not None and tokenizer_source != weights:
        for filename in (
            "config.json",
            "spiece.model",
            "tokenizer_config.json",
            "special_tokens_map.json",
        ):
            source = tokenizer_source / filename
            target = weights / filename
            if source.is_file() and not target.exists():
                target.write_bytes(source.read_bytes())
    return str(weights)


class FineTunedQDMRBackend(BaseQDMRDecomposer):
    """Generate a semicolon-delimited Break string and parse it into steps."""

    def __init__(
        self,
        model_name_or_path: str = "",
        mock: bool = False,
        max_new_tokens: int = 256,
    ):
        self.model_name_or_path = model_name_or_path.strip()
        self._load_path = _resolve_checkpoint(self.model_name_or_path)
        self.mock = mock or not self.model_name_or_path
        self.max_new_tokens = max_new_tokens
        self._tokenizer: Any = None
        self._model: Any = None
        self._load_error: str | None = None
        self.last_raw = ""
        self.last_model_raw = ""
        if not self.mock:
            self._load()

    @property
    def uses_mock(self) -> bool:
        return self._model is None

    def _load(self) -> None:
        _allow_old_torchvision()
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except Exception as exc:
            self._load_error = str(exc)
            self.mock = True
            return
        try:
            tokenizer = AutoTokenizer.from_pretrained(self._load_path)
            model = AutoModelForSeq2SeqLM.from_pretrained(self._load_path)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)
            model.eval()
            self._tokenizer = tokenizer
            self._model = model
        except Exception as exc:
            self._load_error = str(exc)
            self.mock = True
            self._tokenizer = None
            self._model = None

    def generate_break_string(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
    ) -> str:
        """Return the raw semicolon-delimited decomposition."""
        if self._model is None or self._tokenizer is None:
            text = steps_to_break(build_comparative_steps(query, slices, extended_context))
            self.last_raw = text
            return text
        if "break" in self.model_name_or_path.lower() or "break" in self._load_path.lower():
            prompt = f"paraphrase: {query} </s>"
        else:
            prompt = (
                "Decompose the question into Break QDMR steps separated by ' ;'. "
                "Use 'return ...' and cite earlier steps as #1, #2. "
                f"Question: {query}\nContext: {extended_context}"
            )
        import torch

        device = next(self._model.parameters()).device
        encoded = self._tokenizer(prompt, return_tensors="pt", truncation=True).to(device)
        with torch.no_grad():
            output = self._model.generate(**encoded, max_new_tokens=self.max_new_tokens)
        text = self._tokenizer.decode(output[0], skip_special_tokens=True).strip()
        self.last_raw = text
        return text

    def decompose(
        self,
        query: str,
        slices: list[ComparisonSlice],
        extended_context: str = "",
    ) -> list[QDMRStep]:
        fallback = build_comparative_steps(query, slices, extended_context)
        raw = self.generate_break_string(query, slices, extended_context)
        self.last_model_raw = raw
        try:
            parsed = parse_decomposition(raw)
        except Exception:
            self.last_raw = steps_to_break(fallback)
            return fallback
        polished = normalize_break_steps(
            parsed, concept=extended_context, slices=slices
        )
        if steps_are_valid(polished, len(slices)):
            self.last_raw = steps_to_break(polished)
            return polished
        if steps_are_valid(parsed, len(slices)):
            rooted = ensure_synthesize_root(parsed)
            self.last_raw = steps_to_break(rooted)
            return rooted
        self.last_raw = steps_to_break(fallback)
        return fallback
