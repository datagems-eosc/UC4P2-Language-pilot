"""Generic concept extraction. No topic word lists."""

from __future__ import annotations

import re

_QUOTED = re.compile(r'["“”«»]([^"“”«»]+)["“”«»]')
_ORIGIN = re.compile(
    r"\b(?:origin|origins|etymology|history)\s+of\s+(?:the\s+)?"
    r"(?:word\s+|term\s+)?[\"“”«»]?([^\"“”«»?.]+)[\"“”«»]?",
    re.I,
)
_TERM = re.compile(
    r"\b(?:the\s+)?(?:word|term)\s+[\"“”«»]?([A-Za-z][\w'-]*)[\"“”«»]?",
    re.I,
)
_CLIMATE = re.compile(r"\b(?:climate|weather)\s+of\s+(?:the\s+)?(.+?)(?:\s+in\b|\?|$)", re.I)
_OF_PHRASE = re.compile(
    r"\bof\s+(?:the\s+|a\s+|an\s+|the word\s+|the term\s+)?[\"“”«»]?([^\"“”«»?,.;:]+)[\"“”«»]?",
    re.I,
)
_PROPER = re.compile(
    r"\b((?:[A-Z]{2,})|(?:[A-Z][a-z]+(?:(?:\s+|-)[A-Z][a-z]+)*))\b"
)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_TEMPLATES = (
    re.compile(
        r"descriptions of (?:the )?(.+?)"
        r"(?:\s+differ|\s+different|\s+vary|\s+in\b|\s+compared|\?|$)",
        re.I,
    ),
    re.compile(
        r"(?:tracing|reporting|about|regarding|concerning)\s+(?:the |a |an )?"
        r"(?:origin of |origins of |history of )?(?:the word |the term )?(.+?)(?:\?|$)",
        re.I,
    ),
    re.compile(
        r"\b(?:accounts|portrayals)\s+(?:of|about)\s+(?:the |a |an )?(.+?)"
        r"(?:\s+differ|\s+vary|\s+compared|\?|$)",
        re.I,
    ),
    re.compile(r"how did (?:a |an |the )?(.+?) look", re.I),
    re.compile(
        r"how (?:can|could|would|should) (?:the |a |an )?(.+?) be described",
        re.I,
    ),
    re.compile(
        r"how (?:was|were|is|are|did|can|could) (?:a |an |the )?(.+?) "
        r"(?:described|portrayed|represented|framed|differ|defined)",
        re.I,
    ),
    re.compile(r"how (?:is|are|was|were)\s+(?:a |an |the )?(.+?)\s+defined", re.I),
    re.compile(r"who (?:is|are|was|were)\s+(.+?)(?:\?|$)", re.I),
    re.compile(r"what (?:is|are|was|were)\s+(?:a |an |the )?(.+?)(?:\?|$)", re.I),
    re.compile(
        r"\b(?:differences?|contrast)\s+between\s+(?:the |a |an )?(.+?)"
        r"(?:\s+in\b|\s+and\b|\?|$)",
        re.I,
    ),
    re.compile(r"\bwhether\s+(?:the |a |an )?([A-Za-z][\w'-]*)", re.I),
)
_QUESTION_START = {
    "how",
    "what",
    "who",
    "which",
    "where",
    "when",
    "why",
    "were",
    "was",
    "is",
    "are",
    "do",
    "does",
    "did",
    "can",
    "could",
    "would",
    "should",
    "out",
}
_LANGUAGE_NAMES = {
    "german",
    "deutsch",
    "english",
    "englisch",
    "french",
    "spanish",
    "italian",
    "dutch",
    "portuguese",
}
_STOP = frozenset(
    {
        *_QUESTION_START,
        *_LANGUAGE_NAMES,
        "the",
        "a",
        "an",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "with",
        "and",
        "or",
        "as",
        "by",
        "into",
        "over",
        "across",
        "through",
        "out",
        "their",
        "its",
        "his",
        "her",
        "them",
        "they",
        "this",
        "that",
        "these",
        "those",
        "it",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "historical",
        "historically",
        "accounts",
        "account",
        "records",
        "record",
        "sources",
        "source",
        "descriptions",
        "description",
        "entries",
        "entry",
        "vary",
        "varies",
        "varied",
        "differ",
        "differs",
        "different",
        "difference",
        "differences",
        "compared",
        "compare",
        "contrast",
        "versus",
        "vs",
        "tracing",
        "reporting",
        "about",
        "regarding",
        "concerning",
        "whether",
        "today",
        "nowadays",
        "currently",
        "current",
        "present",
        "modern",
        "now",
        "time",
        "times",
        "period",
        "periods",
        "century",
        "centuries",
        "year",
        "years",
        "first",
        "invented",
        "invent",
        "used",
        "term",
        "word",
        "like",
        "look",
        "described",
        "defined",
        "portrayed",
        "represented",
        "framed",
        "broadly",
        "correctly",
        "essentially",
        "common",
        "key",
        "need",
        "needs",
        "place",
        "happen",
        "given",
        "them",
        "process",
        "earlier",
        "later",
        "best",
        "city",
        "live",
        "comes",
        "meaning",
        "today's",
        "todays",
        "western",
        "hemisphere",
        "shift",
        "over",
    }
)


def _clean_concept(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip(" .?!,;:'\"“”«»")
    cleaned = re.sub(
        r"\s+(in|across|over|during|between|from|compared|versus|vs|vary)\b.*$",
        "",
        cleaned,
        flags=re.I,
    ).strip(" .?!,;:'\"“”«»")
    cleaned = re.sub(
        r"\s+(for the first time|in today'?s meaning)\b.*$",
        "",
        cleaned,
        flags=re.I,
    ).strip()
    if cleaned.lower() in {"it", "this", "that", "the", "a", "an"}:
        return ""
    return cleaned


def _quoted_concept(query: str) -> str:
    matches = [_clean_concept(match.group(1)) for match in _QUOTED.finditer(query or "")]
    matches = [item for item in matches if item and len(item.split()) <= 8]
    return matches[-1] if matches else ""


def _proper_names(query: str) -> list[str]:
    names: list[str] = []
    for match in _PROPER.finditer(query or ""):
        name = _clean_concept(match.group(1))
        if not name or name.lower() in _QUESTION_START or name.lower() in _LANGUAGE_NAMES:
            continue
        if name not in names:
            names.append(name)
    return names


def _climate_concept(query: str) -> str:
    if not re.search(r"\b(climate|weather)\b", query or "", re.I):
        return ""
    match = _CLIMATE.search(query or "")
    if match:
        place = _clean_concept(match.group(1))
        if place:
            return f"climate of {place}"
    places = _proper_names(query)
    if len(places) == 1:
        return f"climate of {places[0]}"
    if places:
        return "climate of " + ", ".join(places)
    return "climate"


def _of_concept(query: str) -> str:
    matches = [_clean_concept(match.group(1)) for match in _OF_PHRASE.finditer(query or "")]
    matches = [
        item
        for item in matches
        if item and item.lower() not in _STOP and len(item.split()) <= 8
    ]
    return matches[-1] if matches else ""


def _content_concept(query: str) -> str:
    words = [
        match.group(0)
        for match in _WORD.finditer(query or "")
        if match.group(0).lower() not in _STOP
    ]
    if not words:
        return ""
    return " ".join(words[:6])


def extract_concept(query: str) -> str:
    """Best topic phrase in ``query``. Empty only when the text has no content."""
    text = (query or "").strip()
    if not text:
        return ""
    quoted = _quoted_concept(text)
    if quoted:
        return quoted
    climate = _climate_concept(text)
    if climate:
        return climate
    origin = _ORIGIN.search(text)
    if origin:
        concept = _clean_concept(origin.group(1))
        if concept and concept.lower() not in _STOP:
            return concept
    term = _TERM.search(text)
    if term:
        concept = _clean_concept(term.group(1))
        if concept and concept.lower() not in _STOP:
            return concept
    for pattern in _TEMPLATES:
        match = pattern.search(text)
        if not match:
            continue
        concept = _clean_concept(match.group(1))
        if concept:
            return concept
    names = _proper_names(text)
    if names:
        return names[0] if len(names) == 1 else " ".join(names[:3])
    of_phrase = _of_concept(text)
    if of_phrase:
        return of_phrase
    content = _content_concept(text)
    if content:
        return content
    return _clean_concept(text) or text.rstrip(" ?")


def extract_target_concepts(query: str) -> list[str]:
    concept = extract_concept(query)
    return [concept] if concept else []
