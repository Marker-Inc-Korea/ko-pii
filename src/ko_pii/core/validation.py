"""Validate source-bound extension results before they can affect substitutions."""
from __future__ import annotations

from dataclasses import replace
import math

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.labels import ALL_LABELS


def validated_detection(
    result: object, text: str, *, preserve_metadata: bool = True,
    allow_custom_labels: bool = False,
) -> DetectionResult:
    """Return a detached record or a value-free error, never repair a bad span."""
    if not isinstance(result, DetectionResult):
        raise ValueError("detector must return DetectionResult objects")
    if allow_custom_labels:
        if (not isinstance(result.label, str) or not result.label
                or any(c in result.label for c in "<>\r\n")):
            raise ValueError("detector returned an invalid label")
    elif not isinstance(result.label, str) or result.label not in ALL_LABELS:
        raise ValueError("detector must use an existing ko-pii label")
    if (type(result.start) is not int or type(result.end) is not int
            or not 0 <= result.start < result.end <= len(text)):
        raise ValueError("detector returned an invalid source span")
    if not isinstance(result.text, str) or result.text != text[result.start:result.end]:
        raise ValueError("detector text must equal the source slice")
    if not isinstance(result.risk_level, RiskLevel):
        raise ValueError("detector risk_level must be RiskLevel")
    if (type(result.confidence) not in (int, float) or not 0 <= result.confidence <= 1
            or not math.isfinite(result.confidence)):
        raise ValueError("detector confidence must be finite and between 0 and 1")
    if not preserve_metadata:
        return DetectionResult(result.label, result.text, result.start, result.end,
                               result.risk_level, float(result.confidence))
    if (not isinstance(result.evidence, list) or any(not isinstance(s, str) for s in result.evidence)
            or not isinstance(result.extra, dict) or type(result.normalized) is not bool
            or any(v is not None and not isinstance(v, str)
                   for v in (result.legal_basis, result.rule_id, result.subrule_id))):
        raise ValueError("detector returned invalid metadata")
    # Snapshot each yielded record; generators may reuse and mutate the same one.
    return replace(result, confidence=float(result.confidence),
                   evidence=list(result.evidence), extra=dict(result.extra))
