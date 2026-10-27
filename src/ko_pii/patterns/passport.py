"""여권번호 (Korean Passport Number) detection.

Nine characters: prefix + eight digits, or prefix + three digits + a letter
and four digits (MOFA example: M123A4567). PP/PM/PS are document type codes,
not two-letter passport-number prefixes. This is format detection, not a
checksum, issuance or identity check. Historical G/T numeric candidates are
retained for compatibility; their presence does not prove a valid document.

Sources:
https://passport.go.kr/home/kor/contents.do?menuPos=60
https://learn.microsoft.com/en-us/purview/sit-defn-south-korea-passport-number

Legal basis: 개인정보보호법 시행령 제19조 (고유식별정보 — 여권번호).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PASSPORT"
LEGAL_BASIS = "개인정보보호법 시행령 제19조"
CATEGORY = "고유식별정보"

_MODERN_FORMAT = r"[MSROD][0-9]{3}[A-Z][0-9]{4}"
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    rf"(?:[MSGODRT][0-9]{{8}}|{_MODERN_FORMAT})"
    r"(?![A-Za-z0-9])"
)

_PASSPORT_KIND: dict[str, str] = {
    "M": "general_multiple",
    "S": "general_single",
    "O": "official",
    "D": "diplomatic",
    "R": "resident",
    "T": "travel_cert",
}


def _is_modern_number(text: str) -> bool:
    return re.fullmatch(_MODERN_FORMAT, text) is not None


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        prefix, number = m.group(0)[0], m.group(0)[1:]
        # Reject all-zero serial (placeholder)
        if number == "00000000":
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.CRITICAL,
            confidence=0.9,
            evidence=[
                "pattern:passport",
                f"prefix:{prefix}",
                f"kind:{_PASSPORT_KIND.get(prefix, 'unknown')}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "prefix": prefix,
                "number": number,
                "kind": _PASSPORT_KIND.get(prefix, "unknown"),
                "category": CATEGORY,
            },
        )
