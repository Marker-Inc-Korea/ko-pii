"""외국인등록번호 (Foreign Registration Number) detection.

Format is identical to RRN (13 digits, YYMMDD-SXXXXXC, optional hyphen between
6th and 7th digit). The differentiator is the 7th (century/gender) digit,
which for FRN is restricted to:
  5, 6 → 1900s foreigner (male, female)
  7, 8 → 2000s foreigner

Checksum: same weighted-sum algorithm as RRN; post-2020 randomization applies.

Legal basis: 개인정보보호법 시행령 제19조 (고유식별정보의 범위 — 외국인등록번호),
출입국관리법 제31조.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.checksum.rrn_checksum import is_valid_checksum
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "FRN"
LEGAL_BASIS = "개인정보보호법 시행령 제19조; 출입국관리법 제31조"
CATEGORY = "고유식별정보"

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{6})"
    r"(?:\s?[-.]\s?|[-.\s]{0,2})"   # RRN 과 동일 구분자 규칙(점/공백/래핑 하이픈)
    r"([0-9]{7})"
    r"(?![0-9])"
)

_CENTURY_BY_GENDER_DIGIT: dict[int, int] = {
    5: 1900, 6: 1900,
    7: 2000, 8: 2000,
}


def _decode_birth_date(yymmdd: str, gender_digit: int) -> date | None:
    century_base = _CENTURY_BY_GENDER_DIGIT.get(gender_digit)
    if century_base is None:
        return None
    try:
        return date(
            century_base + int(yymmdd[0:2]),
            int(yymmdd[2:4]),
            int(yymmdd[4:6]),
        )
    except ValueError:
        return None


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        front, back = m.group(1), m.group(2)
        gender_digit = int(back[0])
        birth = _decode_birth_date(front, gender_digit)
        if birth is None:
            continue

        digits_only = front + back
        checksum_ok = is_valid_checksum(digits_only)

        evidence = ["pattern:frn", f"date_valid:{birth.isoformat()}"]
        if checksum_ok:
            evidence.append("checksum:valid")
            confidence = 1.0
        else:
            evidence.append("checksum:invalid_or_post_2020")
            confidence = 0.7

        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.CRITICAL,
            confidence=confidence,
            evidence=evidence,
            legal_basis=LEGAL_BASIS,
            extra={
                "front": front,
                "back": back,
                "birth_date": birth.isoformat(),
                "gender_digit": gender_digit,
                "checksum_valid": checksum_ok,
                "category": CATEGORY,
            },
        )
