"""Comparison slices and N-way query intent."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.retrieval.corpora import dataset_id_for, fill_default_temporal_pair

INDEXED_ARCHIVE_START_YEAR = 1800

_LANGUAGE_ALIASES = {
    "german": "German",
    "deutsch": "German",
    "english": "English",
    "englisch": "English",
    "french": "French",
    "spanish": "Spanish",
    "italian": "Italian",
    "dutch": "Dutch",
    "portuguese": "Portuguese",
}
_PRESENT_MARKERS = (
    "now",
    "today",
    "nowadays",
    "currently",
    "current",
    "modern",
    "present",
)
_UNINDEXED_ERAS = ("medieval", "middle ages", "antiquity", "ancient", "renaissance", "early modern")
_CONCEPT_PATTERNS = (
    re.compile(
        r"descriptions of (?:the )?(.+?)"
        r"(?:\s+differ|\s+different|\s+vary|\s+in\b|\s+compared|\?|$)",
        re.I,
    ),
    re.compile(
        r"(?:reporting|about|regarding|concerning)\s+(?:the |a |an )?(.+?)(?:\?|$)",
        re.I,
    ),
    re.compile(
        r"\b(?:accounts|portrayals)\s+(?:of|about)\s+(?:the |a |an )?(.+?)"
        r"(?:\s+differ|\s+vary|\s+compared|\?|$)",
        re.I,
    ),
    re.compile(r"how did (?:a |an |the )?(.+?) look", re.I),
    re.compile(
        r"how (?:was|were|is|are|did) (?:a |an |the )?(.+?) "
        r"(?:described|portrayed|represented|framed|differ)",
        re.I,
    ),
)
_DECADE = re.compile(r"\b([12]\d{3})'?s\b", re.I)
_CENTURY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+century\b", re.I)
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_LANGUAGE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _LANGUAGE_ALIASES) + r")\b",
    re.I,
)


class ComparisonSlice(BaseModel):
    """One corpus slice in an N-way comparison."""

    slice_id: str
    label: str
    language: str
    period_start: int
    period_end: int
    corpus_id: str = ""


class ParsedQueryIntent(BaseModel):
    """Structured reading of a comparative question."""

    original_query: str
    target_concept: str
    dimension: str
    slices: list[ComparisonSlice] = Field(default_factory=list)


class _Period:
    def __init__(
        self,
        label: str,
        start: Optional[int],
        end: Optional[int],
        unindexed: bool,
        corpus_id: str = "",
    ):
        self.label = label
        self.start = start
        self.end = end
        self.unindexed = unindexed
        self.corpus_id = corpus_id


def _slice_id(index: int) -> str:
    return f"slice_{index + 1}"


def _concept(query: str) -> str:
    for pattern in _CONCEPT_PATTERNS:
        match = pattern.search(query)
        if match:
            text = re.sub(r"\s+", " ", match.group(1)).strip(" .?!,;:'\"")
            text = re.sub(
                r"\s+(in|across|over|during|between|from|compared|versus|vs|vary)\b.*$",
                "",
                text,
                flags=re.I,
            ).strip()
            if text and text.lower() not in {"it", "this", "that"}:
                return text
    if re.search(r"\bmarriage\b", query, re.I):
        return "marriage"
    if re.search(r"\bgalileo\b", query, re.I):
        return "Galileo"
    if re.search(r"\bodin\b", query, re.I):
        return "Odin"
    if re.search(r"\bdresden\b", query, re.I):
        return "Dresden"
    if re.search(r"\b(united states|u\.s\.|usa)\b", query, re.I) or re.search(r"\bUS\b", query):
        return "US"
    return ""


def _languages(query: str) -> list[str]:
    found: list[str] = []
    for match in _LANGUAGE.finditer(query):
        name = _LANGUAGE_ALIASES[match.group(1).lower()]
        if name not in found:
            found.append(name)
    return found


def _periods(query: str, reference: datetime) -> list[_Period]:
    periods: list[_Period] = []
    consumed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(not (end <= left or start >= right) for left, right in consumed)

    for match in _DECADE.finditer(query):
        if overlaps(match.start(), match.end()):
            continue
        start_year = int(match.group(1))
        if start_year % 100 == 0:
            end_year = start_year + 99
        elif start_year % 10 == 0:
            end_year = start_year + 9
        else:
            end_year = start_year
        periods.append(
            _Period(match.group(0), start_year, end_year, start_year < INDEXED_ARCHIVE_START_YEAR)
        )
        consumed.append((match.start(), match.end()))
    for match in _CENTURY.finditer(query):
        if overlaps(match.start(), match.end()):
            continue
        ordinal = int(match.group(1))
        start_year = (ordinal - 1) * 100 + 1
        periods.append(
            _Period(
                match.group(0),
                start_year,
                start_year + 99,
                start_year < INDEXED_ARCHIVE_START_YEAR,
            )
        )
        consumed.append((match.start(), match.end()))
    for match in _YEAR.finditer(query):
        if overlaps(match.start(), match.end()):
            continue
        year = int(match.group(1))
        periods.append(_Period(str(year), year, year, year < INDEXED_ARCHIVE_START_YEAR))
        consumed.append((match.start(), match.end()))
    lowered = query.lower()
    for era in _UNINDEXED_ERAS:
        if era in lowered:
            periods.append(_Period(era, None, None, True))
    if any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in _PRESENT_MARKERS):
        periods.append(_Period("present", reference.year, reference.year, False))
    return periods


def _dimension(languages: list[str], periods: list[_Period], query: str) -> str:
    comparative = bool(
        re.search(
            r"\b(compar\w*|versus|vs\.?|differ\w*|between|vary|varies|varied)\b"
            r"|across time|over time|through time",
            query,
            re.I,
        )
    )
    if len(languages) >= 2 and len(periods) >= 2:
        return "multi-dimensional"
    if len(languages) >= 2 and (comparative or periods):
        return "cross-lingual"
    if len(periods) >= 2 or comparative:
        return "temporal"
    return ""


def _build_slices(
    dimension: str,
    languages: list[str],
    periods: list[_Period],
    corpus_id: str,
) -> list[ComparisonSlice]:
    if dimension == "multi-dimensional":
        pairs = (
            list(zip(languages, periods))
            if len(languages) == len(periods)
            else [(language, period) for period in periods for language in languages]
        )
        return [
            ComparisonSlice(
                slice_id=_slice_id(index),
                label=f"{language} sources, {period.label}",
                language=language,
                period_start=period.start or 0,
                period_end=period.end or period.start or 0,
                corpus_id=corpus_id
                or period.corpus_id
                or dataset_id_for(
                    language=language,
                    period_start=period.start or 0,
                    label=period.label,
                ),
            )
            for index, (language, period) in enumerate(pairs)
            if period.start is not None
        ]
    if dimension == "cross-lingual" and len(languages) >= 2:
        period = periods[0] if periods else None
        start = period.start if period and period.start is not None else 0
        end = period.end if period and period.end is not None else start
        label_period = f", {period.label}" if period else ""
        return [
            ComparisonSlice(
                slice_id=_slice_id(index),
                label=f"{language} sources{label_period}",
                language=language,
                period_start=start,
                period_end=end,
                corpus_id=corpus_id
                or (period.corpus_id if period else "")
                or dataset_id_for(language=language, period_start=start, label=period.label if period else ""),
            )
            for index, language in enumerate(languages)
        ]
    if dimension == "temporal" and len(periods) >= 2:
        slices: list[ComparisonSlice] = []
        for index, period in enumerate(periods):
            if period.start is None:
                continue
            slices.append(
                ComparisonSlice(
                    slice_id=_slice_id(index),
                    label=period.label,
                    language="English",
                    period_start=period.start,
                    period_end=period.end or period.start,
                    corpus_id=corpus_id
                    or period.corpus_id
                    or dataset_id_for(
                        language="English",
                        period_start=period.start,
                        label=period.label,
                    ),
                )
            )
        return slices
    return []


def _period_from_span(span: dict) -> _Period:
    return _Period(
        str(span["label"]),
        int(span["start"]),
        int(span["end"]),
        False,
        corpus_id=str(span.get("corpus_id") or ""),
    )


def _ensure_two_periods(
    periods: list[_Period],
    languages: list[str],
    reference: datetime,
) -> list[_Period]:
    if len(languages) >= 2:
        return periods
    dated = [period for period in periods if period.start is not None]
    if len(dated) >= 2:
        return periods
    language = languages[0] if languages else "English"
    existing = [
        {
            "label": period.label,
            "start": period.start,
            "end": period.end or period.start,
            "corpus_id": period.corpus_id,
        }
        for period in periods
        if period.start is not None
    ]
    filled = fill_default_temporal_pair(existing, language=language, now_year=reference.year)
    return [_period_from_span(span) for span in filled]


def parse_query_intent(
    query: str,
    *,
    reference: datetime | None = None,
    corpus_id: str = "",
) -> tuple[ParsedQueryIntent | None, list[str]]:
    """Parse an N-way comparative question. Errors block retrieval."""
    reference = reference or datetime.now()
    concept = _concept(query)
    languages = _languages(query)
    periods = _ensure_two_periods(_periods(query, reference), languages, reference)
    dimension = _dimension(languages, periods, query)
    slices = _build_slices(dimension, languages, periods, corpus_id)
    errors: list[str] = []
    if not concept:
        errors.append("The target concept to compare is missing or too vague.")
    if not dimension or len(slices) < 2:
        errors.append(
            "A comparison needs at least two slices. Provide two or more periods or source languages."
        )
    offenders = [period.label for period in periods if period.unindexed]
    if offenders:
        listed = ", ".join(offenders)
        errors.append(
            f"The query targets pre-{INDEXED_ARCHIVE_START_YEAR} material ({listed}), "
            f"which is outside the indexed comparative archives. "
            f"Indexed corpora begin in {INDEXED_ARCHIVE_START_YEAR}."
        )
    if errors:
        return None, errors
    return (
        ParsedQueryIntent(
            original_query=query,
            target_concept=concept,
            dimension=dimension,
            slices=slices,
        ),
        [],
    )


def slices_from_disambiguation(payload: dict, *, corpus_id: str = "") -> list[ComparisonSlice]:
    """Map a query-disambiguation language response onto comparison slices."""
    slices: list[ComparisonSlice] = []
    for index, item in enumerate(payload.get("slices") or []):
        start = item.get("start_year")
        end = item.get("end_year")
        if start is None:
            continue
        language = str(item.get("language") or "English")
        label = str(item.get("label") or _slice_id(index))
        slices.append(
            ComparisonSlice(
                slice_id=str(item.get("slice_id") or _slice_id(index)),
                label=label,
                language=language,
                period_start=int(start),
                period_end=int(end if end is not None else start),
                corpus_id=str(item.get("corpus_id") or corpus_id)
                or dataset_id_for(
                    language=language,
                    period_start=int(start),
                    label=label,
                ),
            )
        )
    return slices
