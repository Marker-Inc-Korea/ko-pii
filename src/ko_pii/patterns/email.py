"""Email address detection (simplified RFC 5322).

The full RFC 5322 grammar is complex and includes constructs (quoted local
parts, IP-address domain literals, comments) that essentially never appear in
Korean public-sector documents. This module uses a pragmatic subset.

Legal basis: 개인정보보호법 제2조.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "EMAIL"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+\-])"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)+)"
    r"(?![A-Za-z0-9])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        value = m.group(1)
        local, _, domain = value.rpartition("@")
        # Reject obvious malformed cases the regex permits
        if local.startswith(".") or local.endswith("."):
            continue
        if ".." in local or ".." in domain:
            continue
        yield DetectionResult(
            label=LABEL,
            text=value,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:email"],
            legal_basis=LEGAL_BASIS,
            extra={
                "value": value,
                "local": local,
                "domain": domain,
                "category": CATEGORY,
            },
        )
