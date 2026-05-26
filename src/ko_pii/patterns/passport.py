"""여권번호 (Korean Passport Number) detection.

Format: 1-2 uppercase letter prefix + 8 digits.

Prefix codes (외교부 「여권법」 + 2024.12.16 국제표준 개정):

단일 알파벳 (구 체계 + 일부 현행):
  M  - 일반 복수 여권 (Multiple)
  S  - 일반 단수 여권 (Single)
  G  - 일반 여권 (general, 신형)
  O  - 관용 여권 (Official)
  D  - 외교관 여권 (Diplomatic)
  R  - 거주 여권 (Resident)
  T  - 여행증명서 (Travel certificate, 임시)

두 글자 (외교부 신형):
  PP - 일반 여권 (2024.12.16~ 통일, 단복수 통합)
  PM - 일반 복수 여권 (구 PM 표기)
  PS - 일반 단수 여권 (구 PS 표기)
  PO - 관용 여권
  PD - 외교관 여권
  PR - 거주 여권
  PT - 여행증명서

체크섬은 공개되지 않아 패턴 + prefix 화이트리스트 + 8자리 검증.

Legal basis: 개인정보보호법 시행령 제19조 (고유식별정보 — 여권번호).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PASSPORT"
LEGAL_BASIS = "개인정보보호법 시행령 제19조"
CATEGORY = "고유식별정보"

# 정확한 우선순위: 2자 prefix 먼저 매칭 → 1자 prefix
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(PP|PM|PS|PO|PD|PR|PT|M|S|G|O|D|R|T)"
    r"([0-9]{8})"
    r"(?![A-Za-z0-9])"
)

_PASSPORT_KIND: dict[str, str] = {
    "M": "general_multiple", "PM": "general_multiple", "PP": "general",
    "S": "general_single",   "PS": "general_single",
    "G": "general",
    "O": "official",         "PO": "official",
    "D": "diplomatic",       "PD": "diplomatic",
    "R": "resident",         "PR": "resident",
    "T": "travel_cert",      "PT": "travel_cert",
}


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        prefix = m.group(1)
        number = m.group(2)
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
