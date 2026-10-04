"""Parse Break-style QDMR strings into typed steps.

Accepted forms:

- ``return X ;return #1 where Y``
- lexicon steps such as ``SELECT[papers] ;FILTER[#1, 2020]``
- one ``#k`` instruction per line
"""

from __future__ import annotations

import re

from src.decomposition.base import QDMRStep, reference_ids

OPERATORS = {
    "return",
    "select",
    "filter",
    "project",
    "aggregate",
    "group",
    "superlative",
    "comparative",
    "union",
    "intersection",
    "discard",
    "sort",
    "boolean",
    "arithmetic",
}

_EXPLICIT_INDEX = re.compile(r"^#(\d+)\s+(.*)$", re.S)
_BRACKET = re.compile(r"^([A-Za-z_]+)\[(.*)\]$", re.S)
_LEADING_OPERATOR = re.compile(r"^([A-Za-z_]+)\b\s*(.*)$", re.S)


def split_steps(text: str) -> list[str]:
    """Split a decomposition on semicolons, or on lines when no semicolon is present."""
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    if ";" in raw:
        chunks = raw.split(";")
    else:
        chunks = raw.splitlines()
    return [chunk.strip(" \t-") for chunk in chunks if chunk.strip(" \t-")]


def _split_args(inner: str) -> list[str]:
    arguments: list[str] = []
    buffer: list[str] = []
    depth = 0
    for char in inner:
        if char == "[":
            depth += 1
        elif char == "]":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            arguments.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    tail = "".join(buffer).strip()
    if tail:
        arguments.append(tail)
    return [argument for argument in arguments if argument]


def parse_operator(text: str) -> tuple[str, list[str]]:
    """Return ``(operator, arguments)`` for one step body."""
    bracket = _BRACKET.match(text.strip())
    if bracket and bracket.group(1).lower() in OPERATORS:
        return bracket.group(1).lower(), _split_args(bracket.group(2))
    leading = _LEADING_OPERATOR.match(text.strip())
    if leading and leading.group(1).lower() in OPERATORS:
        rest = leading.group(2).strip()
        return leading.group(1).lower(), [rest] if rest else []
    return "return", [text.strip()] if text.strip() else []


def parse_step(chunk: str, position: int) -> QDMRStep:
    """Parse one chunk. An explicit ``#k`` prefix overrides the positional index."""
    text = chunk.strip()
    explicit = _EXPLICIT_INDEX.match(text)
    if explicit:
        position = int(explicit.group(1))
        text = explicit.group(2).strip()
    operator, arguments = parse_operator(text)
    if operator == "return" and arguments:
        body = arguments[0]
    else:
        body = text
    return QDMRStep(
        step_index=position,
        operator=operator,
        arguments=arguments,
        references=reference_ids(text, exclude=position),
        instruction=f"#{position} {body}",
    )


def parse_decomposition(text: str) -> list[QDMRStep]:
    """Parse a full Break string or a newline list of ``#k`` steps."""
    return [parse_step(chunk, index) for index, chunk in enumerate(split_steps(text), start=1)]


def steps_to_break(steps: list[QDMRStep]) -> str:
    """Serialize steps to a semicolon-delimited Break string."""
    parts: list[str] = []
    for step in steps:
        if step.operator == "return":
            body = step.arguments[0] if step.arguments else step.instruction
            parts.append(f"return {body}")
        elif step.arguments:
            joined = ", ".join(step.arguments)
            parts.append(f"{step.operator.upper()}[{joined}]")
        else:
            parts.append(step.operator.upper())
    return " ;".join(parts)
