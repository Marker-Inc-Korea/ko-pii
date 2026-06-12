"""Tier-2 seam: LLM-based advisory review protocol.

v1 ships the Protocol only. Implementations live OUTSIDE the deterministic hot path:
Guard.check() never calls a reviewer. Wire one in your application layer, after
check() passes, if you want semantic/intent review (e.g. "does this query match
the user's question?"). Advisory by design — a reviewer must never be the only
thing standing between an LLM and your database.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .result import GuardResult


@runtime_checkable
class SemanticReviewer(Protocol):
    """Implement this to plug an LLM (or human) advisory review on top of ko-sqlguard."""

    def review(self, sql: str, intent: str, deterministic_result: GuardResult) -> str:
        """Return an advisory opinion for `sql` given the user `intent`.

        Called only after deterministic checks; must not mutate the result.
        """
        ...
