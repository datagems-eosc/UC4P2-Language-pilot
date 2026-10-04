"""Comparative archive gate and the query-disambiguation API client.

Production runs call ``POST /query_disambiguation/language`` on
dg-query-disambiguation. ``HistoricalComparativeConstraints`` is the local
copy of that gate, used when the service is unreachable and by unit tests.
Meteorological coverage is not applied here.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from src.constraints.base import BaseConstraint

from src.oidc import OIDCTokenError, bearer_token_from_env

INDEXED_ARCHIVE_START_YEAR = 1800
ComparisonType = Literal["temporal", "cross_lingual", "multi-dimensional"]

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
    "present-day",
    "present day",
)
_UNINDEXED_ERAS = (
    "medieval",
    "middle ages",
    "antiquity",
    "ancient",
    "renaissance",
    "early modern",
)
_CONCEPT_PATTERNS = (
    re.compile(
        r"descriptions of (?:the )?(.+?)"
        r"(?:\s+differ|\s+different|\s+in\b|\s+compared|\?|$)",
        re.I,
    ),
    re.compile(r"how did (?:a |an |the )?(.+?) look", re.I),
    re.compile(
        r"how (?:was|were|is|are) (?:a |an |the )?(.+?) "
        r"(?:described|portrayed|represented|framed)",
        re.I,
    ),
)
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_DECADE = re.compile(r"\b([12]\d{3})'?s\b", re.I)
_CENTURY = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+century\b", re.I)
_LANGUAGE = re.compile(
    r"\b(" + "|".join(re.escape(name) for name in _LANGUAGE_ALIASES) + r")\b",
    re.I,
)


class DisambiguationAPIError(RuntimeError):
    """The query-disambiguation service could not be called."""


class CorpusSlice(BaseModel):
    slice_id: str
    label: str
    period: Optional[str] = None
    language: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None


class _PeriodSpan(BaseModel):
    label: str
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    unindexed: bool = False


def _century_start(number: int) -> int:
    return (number - 1) * 100 + 1


def _strip_concept(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip(" .?!,;:'\"")
    return re.sub(
        r"\s+(in|across|over|during|between|from|compared|versus|vs)\b.*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()


def _extract_concepts(query: str) -> list[str]:
    for pattern in _CONCEPT_PATTERNS:
        match = pattern.search(query)
        if not match:
            continue
        concept = _strip_concept(match.group(1))
        if concept and concept.lower() not in {"it", "this", "that"}:
            return [concept]
    lowered = query.lower()
    if re.search(r"\bmarriage\b", lowered):
        return ["marriage"]
    if re.search(r"\b(united states|u\.s\.|usa)\b", lowered) or re.search(r"\bUS\b", query):
        return ["US"]
    return []


def _extract_languages(query: str) -> list[str]:
    found: list[str] = []
    for match in _LANGUAGE.finditer(query):
        canonical = _LANGUAGE_ALIASES[match.group(1).lower()]
        if canonical not in found:
            found.append(canonical)
    return found


def _extract_periods(query: str, reference: datetime) -> list[_PeriodSpan]:
    periods: list[_PeriodSpan] = []
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
            _PeriodSpan(
                label=match.group(0),
                start_year=start_year,
                end_year=end_year,
                unindexed=start_year < INDEXED_ARCHIVE_START_YEAR,
            )
        )
        consumed.append((match.start(), match.end()))

    for match in _CENTURY.finditer(query):
        if overlaps(match.start(), match.end()):
            continue
        start_year = _century_start(int(match.group(1)))
        periods.append(
            _PeriodSpan(
                label=match.group(0),
                start_year=start_year,
                end_year=start_year + 99,
                unindexed=start_year < INDEXED_ARCHIVE_START_YEAR,
            )
        )
        consumed.append((match.start(), match.end()))

    for match in _YEAR.finditer(query):
        if overlaps(match.start(), match.end()):
            continue
        year = int(match.group(1))
        periods.append(
            _PeriodSpan(
                label=str(year),
                start_year=year,
                end_year=year,
                unindexed=year < INDEXED_ARCHIVE_START_YEAR,
            )
        )
        consumed.append((match.start(), match.end()))

    lowered = query.lower()
    for era in _UNINDEXED_ERAS:
        if era in lowered:
            periods.append(_PeriodSpan(label=era, unindexed=True))
    if any(re.search(rf"\b{re.escape(marker)}\b", lowered) for marker in _PRESENT_MARKERS):
        periods.append(
            _PeriodSpan(
                label="present",
                start_year=reference.year,
                end_year=reference.year,
            )
        )
    return periods


def _comparison_type(
    languages: list[str], periods: list[_PeriodSpan], query: str
) -> Optional[ComparisonType]:
    comparative = bool(
        re.search(r"\b(compar\w*|versus|vs\.?|differ\w*|across time)\b", query, re.I)
    )
    if len(languages) >= 2 and len(periods) >= 2:
        return "multi-dimensional"
    if len(languages) >= 2 and (comparative or periods):
        return "cross_lingual"
    if len(periods) >= 2 or (len(periods) == 1 and comparative):
        return "temporal"
    if len(languages) >= 2:
        return "cross_lingual"
    if comparative:
        return "temporal"
    return None


def _slice_id(index: int) -> str:
    return f"slice_{index + 1}"


def _build_slices(
    comparison_type: Optional[ComparisonType],
    languages: list[str],
    periods: list[_PeriodSpan],
) -> list[CorpusSlice]:
    if comparison_type == "multi-dimensional":
        pairs = (
            list(zip(languages, periods))
            if len(languages) == len(periods)
            else [(language, period) for period in periods for language in languages]
        )
        return [
            CorpusSlice(
                slice_id=_slice_id(index),
                label=f"{language} sources, {period.label}",
                period=period.label,
                language=language,
                start_year=period.start_year,
                end_year=period.end_year,
            )
            for index, (language, period) in enumerate(pairs)
            if period.start_year is not None
        ]
    if comparison_type == "cross_lingual" and len(languages) >= 2:
        period = periods[0] if periods else None
        slices: list[CorpusSlice] = []
        for index, language in enumerate(languages):
            label = language + (f" sources, {period.label}" if period else " sources")
            slices.append(
                CorpusSlice(
                    slice_id=_slice_id(index),
                    label=label,
                    period=period.label if period else None,
                    language=language,
                    start_year=period.start_year if period else None,
                    end_year=period.end_year if period else None,
                )
            )
        return slices
    if comparison_type == "temporal" and len(periods) >= 2:
        return [
            CorpusSlice(
                slice_id=_slice_id(index),
                label=period.label,
                period=period.label,
                language="English",
                start_year=period.start_year,
                end_year=period.end_year,
            )
            for index, period in enumerate(periods)
            if period.start_year is not None
        ]
    return []


def _post_json(url: str, payload: dict[str, Any], token: str | None, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DisambiguationAPIError(
            f"Query disambiguation returned HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise DisambiguationAPIError(f"Query disambiguation is unreachable: {exc.reason}") from exc
    if not isinstance(body, dict):
        raise DisambiguationAPIError("Query disambiguation returned a non-object payload.")
    return body


def unwrap_disambiguation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept either the API envelope or a bare result object."""
    result = payload.get("result")
    if isinstance(result, dict) and "proceed" in result:
        return result
    return payload


class QueryDisambiguationClient:
    """Client for ``POST /query_disambiguation/language``."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 60.0,
        use_llm: bool = True,
    ):
        configured = base_url or os.getenv(
            "QUERY_DISAMBIGUATION_URL",
            "https://datagems-dev.scayle.es/query-disambiguation",
        )
        self.base_url = configured.rstrip("/")
        if token is not None:
            self.token = token
        else:
            try:
                self.token = bearer_token_from_env(os.getenv("QUERY_DISAMBIGUATION_TOKEN"))
            except OIDCTokenError:
                self.token = os.getenv("QUERY_DISAMBIGUATION_TOKEN")
        self.timeout = timeout
        self.use_llm = use_llm

    def disambiguate_language(
        self,
        query: str,
        llm_model: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/query_disambiguation/language"
        payload = _post_json(
            url,
            {
                "query": query,
                "llm_model": llm_model,
                "use_llm": self.use_llm,
            },
            self.token,
            self.timeout,
        )
        return unwrap_disambiguation_payload(payload)


class HistoricalComparativeConstraints(BaseConstraint):
    """Check concepts, comparison type, slices, and indexed-archive years."""

    def __init__(
        self,
        *,
        query: str,
        target_concepts: list[str],
        comparison_type: Optional[ComparisonType],
        slices: list[CorpusSlice],
        constraint_errors: list[str],
    ):
        self.query = query
        self.target_concepts = target_concepts
        self.comparison_type = comparison_type
        self.slices = slices
        self.constraint_errors = constraint_errors

    @classmethod
    def from_query(
        cls,
        query: str,
        *,
        reference: datetime | None = None,
    ) -> "HistoricalComparativeConstraints":
        reference = reference or datetime.now()
        concepts = _extract_concepts(query)
        languages = _extract_languages(query)
        periods = _extract_periods(query, reference)
        comparison_type = _comparison_type(languages, periods, query)
        slices = _build_slices(comparison_type, languages, periods)
        errors: list[str] = []
        if not concepts:
            errors.append("The target concept to compare is missing or too vague.")
        if comparison_type is None:
            errors.append(
                "The comparison type is unclear. Specify a temporal contrast "
                "(two periods) or a cross-lingual contrast (two source languages)."
            )
        elif len(slices) < 2:
            errors.append(
                "A comparison needs at least two slices. Provide two or more periods or source languages."
            )
        offenders = [period.label for period in periods if period.unindexed]
        if offenders:
            listed = ", ".join(offenders)
            errors.append(
                f"The query targets pre-{INDEXED_ARCHIVE_START_YEAR} material "
                f"({listed}), which is outside the indexed comparative archives. "
                f"Indexed corpora begin in {INDEXED_ARCHIVE_START_YEAR}."
            )
        return cls(
            query=query,
            target_concepts=concepts,
            comparison_type=comparison_type,
            slices=slices,
            constraint_errors=errors,
        )

    @classmethod
    def from_api(cls, query: str, payload: dict[str, Any]) -> "HistoricalComparativeConstraints":
        result = unwrap_disambiguation_payload(payload)
        slices = [CorpusSlice.model_validate(item) for item in result.get("slices") or []]
        comparison = result.get("comparison_type")
        if comparison not in {"temporal", "cross_lingual", "multi-dimensional"}:
            comparison = None
        return cls(
            query=query,
            target_concepts=list(result.get("target_concepts") or []),
            comparison_type=comparison,
            slices=slices,
            constraint_errors=list(result.get("constraint_errors") or []),
        )

    def validate_boundaries(self) -> list[str]:
        return list(self.constraint_errors)

    def format_clarification(self, errors: list[str]) -> str:
        return (
            "This historical comparative query cannot be executed against the indexed archives. "
            + " ".join(errors)
            + " Please name the concept and restrict each slice to indexed sources from "
            f"{INDEXED_ARCHIVE_START_YEAR} onward, with either two periods or two source languages."
        )

    def to_api_dict(self) -> dict[str, Any]:
        clarification = self.clarification()
        return {
            "domain": "comparative",
            "target_concepts": self.target_concepts,
            "comparison_type": self.comparison_type,
            "slices": [slice_.model_dump() for slice_ in self.slices],
            "constraint_errors": self.constraint_errors,
            "clarification": clarification,
            "proceed": clarification is None,
            "overall_clarity": "low" if clarification else "medium",
            "general_notes": [],
            "ambiguous_parts": [],
            "suggested_queries": [],
        }


class ComparativeGateResult(BaseModel):
    """Normalized gate output consumed by the orchestrator."""

    proceed: bool
    clarification: Optional[str] = None
    target_concepts: list[str] = Field(default_factory=list)
    comparison_type: Optional[str] = None
    slices: list[CorpusSlice] = Field(default_factory=list)
    constraint_errors: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
