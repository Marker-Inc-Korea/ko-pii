"""법인등록번호 (Corporation Registration Number) detection.

13-digit format visually identical to RRN (NNNNNN-NNNNNNN), but the first 6
digits are a registry-office + registration code, not a date.

Disambiguation from RRN/FRN:
  - This module requires the 법인 checksum to pass (Luhn-like, weights 1-2).
  - If the candidate ALSO passes the RRN/FRN checksum AND its first 6 digits
    form a valid calendar date, we treat it as an RRN/FRN and yield nothing
    here. The RRN/FRN modules will claim it.
  - Otherwise (e.g., 한전 191211-0006637: RRN checksum fails) we emit as
    CORP_REG.

Risk level: MEDIUM. 법인등록번호 자체는 일반적으로 개인정보로 분류되지 않지만,
공공기관·법인의 식별 정보로서 일정 수준의 처리 통제가 권고됨.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.checksum.corp_reg_checksum import is_valid_checksum
from ko_pii.checksum.rrn_checksum import is_valid_checksum as is_valid_rrn_checksum
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "CORP_REG"
LEGAL_BASIS = "상법 제40조; 법인등기규칙"
CATEGORY = "법인식별정보"

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{6})"
    r"(?:\s?[-./]\s?|[-./\s]{0,2})"   # RRN 과 동일 구분자(점/슬래시/공백/래핑 하이픈)
    r"([0-9]{7})"
    r"(?![0-9])"
)


def _is_valid_date_prefix(yymmdd: str) -> bool:
    """Return True if YYMMDD could form a real calendar date in any century."""
    mm = int(yymmdd[2:4])
    dd = int(yymmdd[4:6])
    if not (1 <= mm <= 12):
        return False
    if not (1 <= dd <= 31):
        return False
    try:
        date(2000, mm, dd)  # 2000 is a leap year, so Feb 29 is valid
        return True
    except ValueError:
        return False


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        front, back = m.group(1), m.group(2)
        digits = front + back
        # GS1 Bookland(ISBN/ISSN, 978/979 시작)의 무구분자 13자리는 도서 바코드이지
        # 법인등록번호가 아니다 → 제외(법인번호는 978/979 로 시작하지 않아 recall 무해).
        if front[:3] in ("978", "979") and m.group(0) == digits:
            continue
        if not is_valid_checksum(digits):
            continue
        if is_valid_rrn_checksum(digits) and _is_valid_date_prefix(front):
            # An actual RRN/FRN coincidentally passes the 법인 checksum;
            # let the RRN/FRN detector claim it.
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=1.0,
            evidence=["pattern:corp_reg", "checksum:valid"],
            legal_basis=LEGAL_BASIS,
            extra={
                "front": front,
                "back": back,
                "digits": digits,
                "category": CATEGORY,
            },
        )
