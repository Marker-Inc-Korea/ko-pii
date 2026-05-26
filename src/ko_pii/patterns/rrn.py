"""주민등록번호 (Resident Registration Number) detection.

Detection criteria, in order:
  1. Pattern: 13 ASCII digits with an optional hyphen between the 6th and 7th
     digit, with no surrounding digits (prevents matches inside longer numeric
     runs such as credit cards).
  2. Gender/century digit (7th) must indicate a Korean national: {1, 2, 3, 4,
     9, 0}. Foreigner codes {5, 6, 7, 8} are handled by ko_pii.patterns.frn.
  3. Date validity: digits 1..6 must form a real calendar date once the
     century is decoded from the 7th digit.
  4. Checksum: if it passes the standard weighted-sum check, confidence = 1.0;
     otherwise the candidate is still emitted with reduced confidence (0.7),
     because post-2020 RRNs may not satisfy the checksum.

Legal basis: 개인정보보호법 제24조의2 (고유식별정보, 주민등록번호 처리 제한).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.checksum.rrn_checksum import is_valid_checksum
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "RRN"
LEGAL_BASIS = "개인정보보호법 제24조의2"
CATEGORY = "고유식별정보"

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{6})"
    r"[-\s]?"            # 하이픈 / 공백 / 없음
    r"([0-9]{7})"
    r"(?![0-9])"
)

_CENTURY_BY_GENDER_DIGIT: dict[int, int] = {
    1: 1900, 2: 1900,
    3: 2000, 4: 2000,
    9: 1800, 0: 1800,
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
    """Yield a DetectionResult for each plausible RRN found in *text*."""
    for m in _PATTERN.finditer(text):
        front, back = m.group(1), m.group(2)
        gender_digit = int(back[0])
        birth = _decode_birth_date(front, gender_digit)
        if birth is None:
            continue

        digits_only = front + back
        checksum_ok = is_valid_checksum(digits_only)

        evidence = ["pattern:rrn", f"date_valid:{birth.isoformat()}"]
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
