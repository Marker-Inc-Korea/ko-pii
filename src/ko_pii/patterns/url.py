"""URL detection.

Plain URLs (http/https). Marked as INFO/LOW since most URLs themselves are
not PII, but they are emitted so downstream rules can scan path/query for
embedded identifiers (emails, IDs).

Legal basis: 개인정보보호법 제2조 (조합 식별 가능성).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "URL"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

_PATTERN = re.compile(
    r"\bhttps?://[^\s<>\"'`)\]\}]+",
    re.IGNORECASE,
)


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        url = m.group(0).rstrip(".,;:!?")
        yield DetectionResult(
            label=LABEL,
            text=url,
            start=m.start(),
            end=m.start() + len(url),
            risk_level=RiskLevel.INFO,
            confidence=0.9,
            evidence=["pattern:url"],
            legal_basis=LEGAL_BASIS,
            extra={
                "url": url,
                "scheme": url.split("://", 1)[0].lower(),
                "category": CATEGORY,
            },
        )
