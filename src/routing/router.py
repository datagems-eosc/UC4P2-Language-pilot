"""Route every question in this pilot onto the comparative path."""

from __future__ import annotations

from typing import Any

import dspy
from pydantic import BaseModel, Field

from src.schemas.concept import extract_concept


class DomainRouter(dspy.Signature):
    """Extract the concept being compared. This pilot has no meteorological route."""

    query: str = dspy.InputField()
    concept: str = dspy.OutputField(desc="The concept being compared, or empty if unclear")


class RouteDecision(BaseModel):
    domain: str = "comparative"
    concept: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


def route_query(query: str) -> RouteDecision:
    """Mark the question as comparative. Concept comes from the wording, or an LM."""
    heuristic = extract_concept(query) or None
    if getattr(dspy.settings, "lm", None) is None:
        return RouteDecision(domain="comparative", concept=heuristic)
    try:
        prediction = dspy.Predict(DomainRouter)(query=query)
    except Exception:
        return RouteDecision(domain="comparative", concept=heuristic)
    concept = str(getattr(prediction, "concept", "") or "").strip() or heuristic
    return RouteDecision(domain="comparative", concept=concept)
