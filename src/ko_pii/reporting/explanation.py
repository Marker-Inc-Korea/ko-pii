"""Versioned value-free report of observed decisions, not an anonymity claim."""
from __future__ import annotations

import math
from typing import Any

from ko_pii.anonymizer import AnonymizationResult
from ko_pii.core.modes import Action, ProcessingMode
from ko_pii.labels import ALL_LABELS
from ko_pii.policy import STRATEGIES
from ko_pii.core.trace import RULE_IDS, SUBRULE_IDS

_CHECKS = frozenset({"checksum:valid", "checksum:invalid_or_post_2020", "checksum:luhn_valid",
                     "obfuscated:deobfuscated", "field:asserted"})


def explain(result: AnonymizationResult, *, include_trace: bool = False) -> dict[str, Any]:
    """Export only allowlisted metadata; text, tokens, evidence and extra stay local.

    Rule IDs identify families; subrule IDs cover the documented email paths.
    Optional traces cover common overlap resolution, not every rejection/miss.
    """
    spans = {(s.start, s.end): s for s in result.substitutions}
    rows = []
    for record in result.detections:
        d = record.detection
        span = spans.get((d.start, d.end)) if record.action == Action.BLOCK else None
        selected = record.strategy or result.summary.get("strategy")
        strategy = selected if isinstance(selected, str) and selected in STRATEGIES else None
        if span is None:
            reason = "not_selected_for_substitution" if record.action == Action.BLOCK else "retained_by_policy"
        elif strategy == "partial":
            reason = "partial_masking"
        else:
            reason = "substituted"
        rows.append({
            "label": d.label if d.label in ALL_LABELS else "UNKNOWN",
            "rule_id": d.rule_id if d.rule_id in RULE_IDS else None,
            "subrule_id": d.subrule_id if d.subrule_id in SUBRULE_IDS else None,
            "source_span": [d.start, d.end],
            "output_span": [span.output_start, span.output_end] if span else None,
            "normalized": bool(d.normalized),
            "checks": sorted({item for item in d.evidence if item in _CHECKS}),
            "confidence": d.confidence if math.isfinite(d.confidence) else None,
            "action": record.action.value,
            "requested_strategy": strategy,
            "applied_strategy": strategy if span else None,
            "reason": reason,
        })
    mode = result.summary.get("mode")
    priority = ("block_risk_confidence_length_start"
                if result.summary.get("overlap_resolution") == "block_risk_confidence_length_start"
                else "risk_confidence_length_start")
    report = {
        "schema_version": 1,
        "contract": "ko-pii-explanation-v1",
        "scope": "selected_detections_only",
        "overlap_resolution": f"{priority}; discarded_candidates_not_included",
        "offset_unit": "python_code_points",
        "mode": mode if mode in {m.value for m in ProcessingMode} else None,
        "detection_count": len(rows),
        "substitution_count": sum(row["output_span"] is not None for row in rows),
        "findings": rows,
    }
    if include_trace:
        report["overlap_trace"] = result.overlap_trace.report() if result.overlap_trace is not None else None
    return report
