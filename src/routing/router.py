"""Route every question in this pilot onto the comparative path."""

from __future__ import annotations

from typing import Any

import dspy
from pydantic import BaseModel, Field


class DomainRouter(dspy.Signature):
    """Extract the concept being compared. This pilot has no meteorological route."""

    query: str = dspy.InputField()
    concept: str = dspy.OutputField(desc="The concept being compared, or empty if unclear")


class RouteDecision(BaseModel):
    domain: str = "comparative"
    concept: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def route_query(query: str) -> RouteDecision:
    """Mark the question as comparative. An LM may suggest the concept."""
    if getattr(dspy.settings, "lm", None) is None:
        return RouteDecision(domain="comparative")
    try:
        prediction = dspy.Predict(DomainRouter)(query=query)
    except Exception:
        return RouteDecision(domain="comparative")
    concept = str(getattr(prediction, "concept", "") or "").strip() or None
    return RouteDecision(domain="comparative", concept=concept)
