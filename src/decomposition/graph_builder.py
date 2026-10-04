"""Topological schedule for a QDMR dependency graph."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from pydantic import BaseModel, Field

from src.decomposition.base import QDMRStep


class QDMRGraph(BaseModel):
    """DAG of QDMR steps. An edge ``(source, target)`` means target depends on source."""

    steps: list[QDMRStep]
    edges: list[tuple[int, int]] = Field(default_factory=list)


def build_graph(steps: list[QDMRStep]) -> QDMRGraph:
    """Index steps and record a dependency edge for every ``#k`` reference."""
    indexes = [step.step_index for step in steps]
    if len(indexes) != len(set(indexes)):
        raise ValueError("QDMR steps must have unique indexes.")
    known = set(indexes)
    edges: list[tuple[int, int]] = []
    for step in steps:
        for ref in step.references:
            if ref not in known:
                raise ValueError(f"Step #{step.step_index} references missing step #{ref}.")
            if ref >= step.step_index:
                raise ValueError(
                    f"Step #{step.step_index} has a forward reference to #{ref}."
                )
            edges.append((ref, step.step_index))
    return QDMRGraph(steps=list(steps), edges=edges)


def schedule(steps: list[QDMRStep]) -> list[list[QDMRStep]]:
    """Group steps into layers. Steps in one layer have no dependency on each other."""
    graph = build_graph(steps)
    pending = {step.step_index: step for step in graph.steps}
    done: set[int] = set()
    layers: list[list[QDMRStep]] = []
    while pending:
        ready = [
            pending[index]
            for index in sorted(pending)
            if all(ref in done for ref in pending[index].references)
        ]
        if not ready:
            raise ValueError("QDMR graph contains a cycle.")
        layers.append(ready)
        for step in ready:
            done.add(step.step_index)
            del pending[step.step_index]
    return layers


def format_tree(steps: list[QDMRStep]) -> str:
    """Render a plan as a tree. The final step is the root; ``#k`` steps sit under it.

    A step used by more than one later step is repeated under each parent.
    """
    by_index = {step.step_index: step for step in steps}
    referenced = {ref for step in steps for ref in step.references}
    roots = [step for step in steps if step.step_index not in referenced] or list(steps)
    lines: list[str] = []

    def walk(step: QDMRStep, prefix: str, child_prefix: str, ancestors: set[int]) -> None:
        lines.append(f"{prefix}{step.instruction}")
        if step.step_index in ancestors:
            return
        children = [by_index[ref] for ref in step.references if ref in by_index]
        next_ancestors = ancestors | {step.step_index}
        for index, child in enumerate(children):
            last = index == len(children) - 1
            branch = "└── " if last else "├── "
            extension = "    " if last else "│   "
            walk(child, child_prefix + branch, child_prefix + extension, next_ancestors)

    for index, root in enumerate(roots):
        if index:
            lines.append("")
        walk(root, "", "", set())
    return "\n".join(lines)


class QDMRExecutionRunner:
    """Run a handler over the schedule.

    Layers run one after another. Steps inside a layer run together when
    ``parallel`` is true, and in index order otherwise.
    """

    def __init__(self, parallel: bool = True):
        self.parallel = parallel

    def run(
        self,
        steps: list[QDMRStep],
        handler: Callable[[QDMRStep, Mapping[int, Any]], Any],
    ) -> dict[int, Any]:
        results: dict[int, Any] = {}
        for layer in schedule(steps):
            if self.parallel and len(layer) > 1:
                snapshot = dict(results)
                with ThreadPoolExecutor(max_workers=len(layer)) as pool:
                    futures = {
                        pool.submit(handler, step, snapshot): step for step in layer
                    }
                    for future in as_completed(futures):
                        step = futures[future]
                        results[step.step_index] = future.result()
            else:
                for step in layer:
                    results[step.step_index] = handler(step, results)
        return results
