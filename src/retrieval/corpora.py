"""Language corpora indexed in Cross-Dataset Discovery."""

from __future__ import annotations

from typing import Any

LANGUAGE_DATASETS: dict[str, dict[str, Any]] = {
    "encyc": {
        "key": "Encyc",
        "name": "EncycNet",
        "uuid": "07382b91-5bc5-42f9-8391-33adc2460c19",
        "languages": ("German",),
        "era": "historical",
    },
    "kp": {
        "key": "Kp",
        "name": "19th C. Knowledge Project (Britannica)",
        "uuid": "d84d1a2e-127d-4393-91d0-afb7e4fd9c68",
        "languages": ("English",),
        "era": "historical",
    },
    "diderot": {
        "key": "Diderot",
        "name": "Encyclopédie (Diderot)",
        "uuid": "d5c34990-9acf-4349-91d4-924f58565922",
        "languages": ("French",),
        "era": "historical",
    },
    "wiki": {
        "key": "Wiki",
        "name": "Wikipedia",
        "uuid": "1f6fba0c-9aea-4345-b5a3-457c924f9e0c",
        "languages": ("English", "German", "French"),
        "era": "present",
    },
}

ALL_LANGUAGE_DATASET_IDS: tuple[str, ...] = tuple(
    item["uuid"] for item in LANGUAGE_DATASETS.values()
)

_PRESENT_LABELS = {"now", "today", "nowadays", "currently", "current", "modern", "present"}
_KNOWN_UUIDS = {item["uuid"] for item in LANGUAGE_DATASETS.values()}


def is_present_era(label: str = "", period_start: int = 0) -> bool:
    folded = (label or "").strip().lower()
    if any(marker in folded for marker in _PRESENT_LABELS):
        return True
    return period_start >= 2000


def dataset_id_for(
    *,
    language: str = "English",
    period_start: int = 0,
    label: str = "",
    corpus_id: str = "",
) -> str:
    """Pick EncycNet / KP / Diderot / Wikipedia from language and period."""
    if corpus_id in _KNOWN_UUIDS:
        return corpus_id
    if is_present_era(label, period_start):
        return LANGUAGE_DATASETS["wiki"]["uuid"]
    folded = (language or "English").strip().lower()
    if folded.startswith("german") or folded.startswith("deutsch"):
        return LANGUAGE_DATASETS["encyc"]["uuid"]
    if folded.startswith("french") or folded.startswith("français"):
        return LANGUAGE_DATASETS["diderot"]["uuid"]
    return LANGUAGE_DATASETS["kp"]["uuid"]


def dataset_ids_for_slice(slice_: Any) -> list[str]:
    return [
        dataset_id_for(
            language=getattr(slice_, "language", "") or "English",
            period_start=int(getattr(slice_, "period_start", 0) or 0),
            label=getattr(slice_, "label", "") or "",
            corpus_id=getattr(slice_, "corpus_id", "") or "",
        )
    ]
