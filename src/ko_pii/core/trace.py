"""Bounded, value-free metadata for common overlap resolution only."""
from __future__ import annotations

from typing import Any

from ko_pii.core.types import DetectionResult
from ko_pii.labels import ALL_LABELS

RULE_IDS = frozenset({f"ko-pii.{label.lower()}.v1" for label in ALL_LABELS} | {"field.asserted.v1"})
SUBRULE_IDS = frozenset({"email.ascii.v1", "email.korean_domain.v1", "email.obfuscated.v1"})


def validate_trace_limit(limit: int) -> None:
    if type(limit) is not int or not 0 <= limit <= 1000:
        raise ValueError("trace_limit must be an integer between 0 and 1000")


def _metadata(d: DetectionResult) -> dict[str, Any]:
    return {"label": d.label if d.label in ALL_LABELS else "UNKNOWN",
            "rule_id": d.rule_id if d.rule_id in RULE_IDS else None,
            "subrule_id": d.subrule_id if d.subrule_id in SUBRULE_IDS else None,
            "source_span": [d.start, d.end]}


class OverlapTrace:
    """Counts include all candidates; only discarded metadata consumes the cap.

    A blocker is one accepted overlapping candidate at that resolution stage,
    not necessarily the sole blocker or a final output detection.
    """

    def __init__(self, limit: int = 100) -> None:
        validate_trace_limit(limit)
        self._limit = limit
        self._events: list[dict[str, Any]] = []
        self._discarded = 0
        self._stages: dict[str, dict[str, int]] = {}

    def record(self, candidate: DetectionResult, blocker: DetectionResult | None, stage: str) -> None:
        if stage not in {"primary", "hybrid"}:
            raise ValueError("unknown overlap stage")
        counts = self._stages.setdefault(stage, {"candidates": 0, "kept": 0, "discarded": 0})
        counts["candidates"] += 1
        counts["kept" if blocker is None else "discarded"] += 1
        if blocker is None:
            return
        self._discarded += 1
        if len(self._events) >= self._limit:
            return
        if candidate.risk_level != blocker.risk_level:
            reason = "lower_risk_priority"
        elif candidate.confidence != blocker.confidence:
            reason = "lower_confidence_priority"
        elif candidate.length != blocker.length:
            reason = "shorter_span_priority"
        elif candidate.start != blocker.start:
            reason = "later_start_priority"
        else:
            reason = "stable_input_order_tie"
        self._events.append({"stage": stage, "reason": reason,
                             "candidate": _metadata(candidate), "blocker": _metadata(blocker)})

    def report(self) -> dict[str, Any]:
        from copy import deepcopy
        return {"schema_version": 1, "contract": "ko-pii-overlap-trace-v1",
                "scope": "common_overlap_only; excludes_detector_internal_and_merge_policy_rejections",
                "limit": self._limit, "truncated": self._discarded > len(self._events),
                "omitted_events": self._discarded - len(self._events),
                "stages": deepcopy(self._stages), "discarded": deepcopy(self._events)}
