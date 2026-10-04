"""Layered SVG graph for a QDMR plan.

Steps in one row do not depend on each other. An arrow runs from a step to
each later step that cites it as ``#k``.
"""

from __future__ import annotations

import html
import itertools

from src.decomposition.base import QDMRStep
from src.decomposition.graph_builder import build_graph, schedule

_NODE_WIDTH = 240
_NODE_GAP = 28
_LAYER_GAP = 64
_MARGIN = 20
_LINE_HEIGHT = 18
_CHARS = 32
_ids = itertools.count()


def _body(step: QDMRStep) -> str:
    prefix = f"#{step.step_index} "
    text = step.instruction.strip()
    if text.startswith(prefix):
        text = text[len(prefix) :].strip()
    return text


def _wrap(text: str, width: int = _CHARS) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines[:5] or [""]


def _node_height(line_count: int) -> int:
    return 40 + line_count * _LINE_HEIGHT


def render_graph(steps: list[QDMRStep], title: str = "", tone: str = "model") -> str:
    """Return an HTML fragment with one layered dependency graph."""
    if not steps:
        return f"<p>{html.escape(title)}</p>" if title else ""
    layers = schedule(steps)
    graph = build_graph(steps)
    boxes: dict[int, tuple[int, int, int, int]] = {}
    wrapped = {step.step_index: _wrap(_body(step)) for step in steps}
    heights = {
        step.step_index: _node_height(len(wrapped[step.step_index])) for step in steps
    }
    widest = max(len(layer) for layer in layers)
    width = _MARGIN * 2 + widest * _NODE_WIDTH + max(0, widest - 1) * _NODE_GAP
    y = _MARGIN + (28 if title else 0)
    for layer in layers:
        row_height = max(heights[step.step_index] for step in layer)
        row_width = len(layer) * _NODE_WIDTH + max(0, len(layer) - 1) * _NODE_GAP
        x = (width - row_width) // 2
        for step in layer:
            boxes[step.step_index] = (x, y, _NODE_WIDTH, heights[step.step_index])
            x += _NODE_WIDTH + _NODE_GAP
        y += row_height + _LAYER_GAP
    height = y - _LAYER_GAP + _MARGIN
    marker = f"arrow-{next(_ids)}"
    last_layer = {step.step_index for step in layers[-1]}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">',
        "<defs>",
        f'<marker id="{marker}" viewBox="0 0 8 8" refX="7" refY="4" '
        f'markerWidth="8" markerHeight="8" orient="auto-start-reverse">',
        '<path d="M1 1 L7 4 L1 7 Z" fill="#5b6570"/>',
        "</marker>",
        "</defs>",
        f'<rect width="{width}" height="{height}" rx="12" fill="#fbfaf7"/>',
    ]
    if title:
        parts.append(
            f'<text x="{_MARGIN}" y="24" font-family="ui-sans-serif, sans-serif" '
            f'font-size="15" font-weight="600" fill="#1c2430">{html.escape(title)}</text>'
        )
    for source, target in graph.edges:
        x1, y1, w1, h1 = boxes[source]
        x2, y2, w2, _h2 = boxes[target]
        start_x, start_y = x1 + w1 / 2, y1 + h1
        end_x, end_y = x2 + w2 / 2, y2
        bend = (start_y + end_y) / 2
        parts.append(
            f'<path d="M {start_x:.1f} {start_y:.1f} C {start_x:.1f} {bend:.1f}, '
            f'{end_x:.1f} {bend:.1f}, {end_x:.1f} {end_y:.1f}" fill="none" '
            f'stroke="#5b6570" stroke-width="1.4" marker-end="url(#{marker})"/>'
        )
    for step in steps:
        x, y, w, h = boxes[step.step_index]
        is_synthesize = step.step_index in last_layer and len(layers) > 1
        if tone == "gold":
            fill = "#f3e7c9" if is_synthesize else "#f8f1dc"
            stroke = "#8a5a2b"
        else:
            fill = "#e7f4ee" if is_synthesize else "#e7f0fb"
            stroke = "#0f6e56" if is_synthesize else "#1d4e89"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
        )
        label = f"#{step.step_index} synthesize" if is_synthesize else f"#{step.step_index}"
        parts.append(
            f'<text x="{x + 14}" y="{y + 22}" font-family="ui-sans-serif, sans-serif" '
            f'font-size="13" font-weight="700" fill="{stroke}">{html.escape(label)}</text>'
        )
        for index, line in enumerate(wrapped[step.step_index]):
            parts.append(
                f'<text x="{x + 14}" y="{y + 42 + index * _LINE_HEIGHT}" '
                f'font-family="ui-sans-serif, sans-serif" font-size="13" fill="#1c2430">'
                f"{html.escape(line)}</text>"
            )
    parts.append("</svg>")
    return (
        '<div style="overflow-x:auto;margin:8px 0 18px">' + "".join(parts) + "</div>"
    )


def render_pair(
    left: list[QDMRStep],
    right: list[QDMRStep],
    left_title: str = "Ground truth",
    right_title: str = "Final sub-questions",
) -> str:
    """Place the benchmark graph beside the rewritten graph."""
    return (
        '<div style="display:flex;gap:20px;align-items:flex-start;overflow-x:auto">'
        + render_graph(left, left_title, tone="gold")
        + render_graph(right, right_title)
        + "</div>"
    )
