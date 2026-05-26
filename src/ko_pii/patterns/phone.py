"""한국 전화번호 detection (휴대전화 / 일반전화 / 인터넷전화 / 국제 형식).

Covered formats:
  - Mobile (휴대전화): 010·011·016·017·018·019 + 7~8 digits
  - Seoul landline: 02 + 7~8 digits
  - Regional landline: 031~033, 041~044, 051~055, 061~064 + 7~8 digits
  - VoIP (인터넷전화): 070 + 8 digits
  - International: +82 / 0082 prefix → 모바일/일반 모두 지원

Separators: hyphen, dot, space, or none. Each emitted DetectionResult carries
its sub-type in `extra["type"]` ∈ {"mobile", "landline", "voip"}, and the
international flag in ``extra["international"]``.

Legal basis: 개인정보보호법 제2조 (개인 식별 정보).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PHONE"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

# International prefix: +82, 0082, or 82- (less common). The body strips the
# leading 0 of the area code per ITU-T E.123 conventions.
_INTL_PREFIX = r"(?:\+82|0082|82)[-.\s]?"

_MOBILE = re.compile(
    r"(?<![0-9+])"
    r"(01[01679])"
    r"[-.\s]?"
    r"(\d{3,4})"
    r"[-.\s]?"
    r"(\d{4})"
    r"(?![0-9])"
)

_MOBILE_INTL = re.compile(
    r"(?<![0-9])"
    + _INTL_PREFIX +
    r"(1[01679])"  # leading 0 dropped under intl prefix
    r"[-.\s]?"
    r"(\d{3,4})"
    r"[-.\s]?"
    r"(\d{4})"
    r"(?![0-9])"
)

_SEOUL = re.compile(
    r"(?<![0-9+])"
    r"(02)"
    r"[-.\s]?"
    r"(\d{3,4})"
    r"[-.\s]?"
    r"(\d{4})"
    r"(?![0-9])"
)

_REGIONAL = re.compile(
    r"(?<![0-9+])"
    r"(03[1-3]|04[1-4]|05[1-5]|06[1-4]|070)"
    r"[-.\s]?"
    r"(\d{3,4})"
    r"[-.\s]?"
    r"(\d{4})"
    r"(?![0-9])"
)

# 대표번호 (15xx/16xx/17xx/18xx) — 8자리, 사업장/콜센터
# KISA 번호자원관리 가이드: 1500-1899 대역
_REPRESENTATIVE = re.compile(
    r"(?<![0-9+])"
    r"(1[5-8]\d{2})"
    r"[-.\s]?"
    r"(\d{4})"
    r"(?![0-9])"
)


def _emit(m: re.Match, phone_type: str, international: bool = False) -> DetectionResult:
    digits = re.sub(r"\D", "", m.group(0))
    ev = ["pattern:phone", f"type:{phone_type}"]
    if international:
        ev.append("intl:+82")
    # 위험도 분기 — 휴대전화는 개인 직통 (HIGH), 유선/VoIP 는 가입자 추적
    # 가능하지만 사업장·대표번호 케이스 다수 (MEDIUM).
    risk = RiskLevel.HIGH if phone_type == "mobile" else RiskLevel.MEDIUM
    return DetectionResult(
        label=LABEL,
        text=m.group(0),
        start=m.start(),
        end=m.end(),
        risk_level=risk,
        confidence=1.0,
        evidence=ev,
        legal_basis=LEGAL_BASIS,
        extra={
            "type": phone_type,
            "prefix": m.group(1),
            "digits_only": digits,
            "international": international,
            "category": CATEGORY,
        },
    )


def _overlaps(span: tuple[int, int], seen: set[tuple[int, int]]) -> bool:
    s, e = span
    for ss, ee in seen:
        if s < ee and ss < e:
            return True
    return False


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    # International forms first — they cover their domestic-looking core.
    for m in _MOBILE_INTL.finditer(text):
        span = (m.start(), m.end())
        if _overlaps(span, seen):
            continue
        seen.add(span)
        yield _emit(m, "mobile", international=True)

    for m in _MOBILE.finditer(text):
        span = (m.start(), m.end())
        if _overlaps(span, seen):
            continue
        seen.add(span)
        yield _emit(m, "mobile")

    for m in _REGIONAL.finditer(text):
        span = (m.start(), m.end())
        if _overlaps(span, seen):
            continue
        seen.add(span)
        prefix = m.group(1)
        yield _emit(m, "voip" if prefix == "070" else "landline")

    for m in _SEOUL.finditer(text):
        span = (m.start(), m.end())
        if _overlaps(span, seen):
            continue
        seen.add(span)
        yield _emit(m, "landline")

    for m in _REPRESENTATIVE.finditer(text):
        span = (m.start(), m.end())
        if _overlaps(span, seen):
            continue
        seen.add(span)
        yield _emit(m, "representative")
