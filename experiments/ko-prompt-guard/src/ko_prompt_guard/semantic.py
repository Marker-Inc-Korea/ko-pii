"""Tier-2 seam: semantic / LLM advisory review.

v1 ships the Protocol only. The deterministic Guard.check() never calls a
reviewer — it stays pure (no network, no model). Wire one in your application
layer, AFTER check() runs, to catch semantic attacks that normalization + rules
cannot (role-play, novel phrasing). Advisory by design: a reviewer must never be
the only thing between an attacker and your LLM.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .result import GuardResult


@runtime_checkable
class SemanticReviewer(Protocol):
    """Implement this to plug an embedding/LLM advisory review on top."""

    def review(self, text: str, deterministic_result: GuardResult) -> float:
        """Return a 0..1 risk score for ``text`` (the de-obfuscated input).

        Called only after deterministic checks; must not mutate the result.
        Compare against ``GuardPolicy.embedding_threshold`` in your app layer.
        """
        ...
