"""Abstract constraint gate used before retrieval."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConstraint(ABC):
    """A domain gate that either passes or returns a clarification."""

    @abstractmethod
    def validate_boundaries(self) -> list[str]:
        """Return human-readable boundary violations. Empty means the query may proceed."""

    def clarification(self) -> str | None:
        """Targeted clarification when validation fails, otherwise None."""
        errors = self.validate_boundaries()
        if not errors:
            return None
        return self.format_clarification(errors)

    @abstractmethod
    def format_clarification(self, errors: list[str]) -> str:
        """Turn boundary errors into one message for the user."""
