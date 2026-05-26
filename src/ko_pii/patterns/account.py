"""은행 계좌번호 (Bank Account Number) — keyword-anchored.

매칭 anchor (둘 중 하나라도 통과):
1. "계좌" / "계좌번호" / "계좌번" 키워드 직전
2. 한국 은행명 키워드 (농협/신한/국민/우리/하나/카뱅/토스 등) — 숫자 *앞 또는 뒤*

대화체에서 흔한 표기를 모두 커버:
  계좌: 110-123-456789
  계좌번호 1234567890
  신한 110-123-456789           (은행명 앞)
  110-123-456789 농협은행        (은행명 뒤)
  카뱅 3333-12-1234567

Legal basis: 개인정보보호법 제2조; 금융실명거래 및 비밀보장에 관한 법률.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "ACCOUNT"
LEGAL_BASIS = "개인정보보호법 제2조; 금융실명법"
CATEGORY = "일반개인정보"

# 한국 은행·금융기관 키워드 — 정확한 명칭 + 약칭 모두 포함.
# 짧은 약칭 (KB, NH 등) 은 단어 경계 충돌 위험으로 제외.
_BANK_NAMES = (
    # 시중은행 (정식·약칭)
    "국민은행", "신한은행", "우리은행", "하나은행", "기업은행", "IBK",
    "KEB하나은행", "KEB", "KB국민은행", "KB",
    "농협은행", "농협", "NH농협", "NH",
    "수협은행", "수협", "Sh수협",
    "SC제일은행", "제일은행", "씨티은행", "한국씨티", "외환은행", "스탠다드차타드",
    # 인터넷은행
    "카카오뱅크", "카뱅", "카카오페이",
    "토스뱅크", "토스뱅킹", "토스페이",
    "케이뱅크", "K뱅크",
    "네이버페이",
    # 지방은행
    "부산은행", "BNK부산", "대구은행", "DGB대구", "경남은행", "BNK경남",
    "광주은행", "전북은행", "제주은행", "JB제주",
    # 특수은행·기관
    "산업은행", "KDB산업", "수출입은행", "EXIM",
    "한국은행", "BOK",
    "우체국", "우정사업본부", "우정청",
    # 상호금융
    "새마을금고", "MG새마을", "MG", "신협", "신용협동조합",
    "수산업협동조합", "농업협동조합",
    # 일부 약칭/통칭 (한국어 약칭만, 영문 약칭은 단어 경계 충돌 위험으로 별도)
    "국민", "신한", "우리", "하나",
)

# anchor 1: "계좌" 키워드가 *직전* 에 (콜론·번호 옵션 허용)
_KEYWORD_PATTERN = re.compile(
    r"(?:계좌\s*(?:번호|번)?\s*:?\s*)"
    r"([0-9][\s\-]*(?:[0-9][\s\-]*){9,19})"
)

# anchor 2: 은행명이 *앞* 에 (선택적 콜론·공백)
_BANK_BEFORE_PATTERN = re.compile(
    r"(?:" + "|".join(map(re.escape, _BANK_NAMES)) + r")"
    r"\s*:?\s*"
    r"([0-9]+(?:[\s\-][0-9]+){1,4}|[0-9]{10,16})"
)

# anchor 3: 은행명이 *뒤* 에 (숫자 + 공백/콤마 옵션 + 은행명)
_BANK_AFTER_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]+(?:[\s\-][0-9]+){1,4}|[0-9]{10,16})"
    r"\s*"
    r"(?:" + "|".join(map(re.escape, _BANK_NAMES)) + r")"
)


def _normalize_and_check(raw: str) -> str | None:
    """공백/하이픈 제거 후 10~16자리 숫자만 반환."""
    digits = re.sub(r"[\s\-]", "", raw)
    if not digits.isdigit():
        return None
    if not (10 <= len(digits) <= 16):
        return None
    return digits


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    # 1) "계좌" 키워드 anchor
    for m in _KEYWORD_PATTERN.finditer(text):
        raw = m.group(1).rstrip()
        digits = _normalize_and_check(raw)
        if digits is None:
            continue
        span = (m.start(1), m.start(1) + len(raw))
        if span in seen:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL, text=raw, start=span[0], end=span[1],
            risk_level=RiskLevel.HIGH, confidence=0.9,
            evidence=["pattern:account", "keyword:계좌"],
            legal_basis=LEGAL_BASIS,
            extra={"digits": digits, "length": len(digits), "category": CATEGORY},
        )

    # 2) 은행명 anchor (앞)
    for m in _BANK_BEFORE_PATTERN.finditer(text):
        raw = m.group(1).rstrip()
        digits = _normalize_and_check(raw)
        if digits is None:
            continue
        span = (m.start(1), m.start(1) + len(raw))
        if span in seen or any(s < span[1] and span[0] < e for s, e in seen):
            continue
        seen.add(span)
        bank = m.group(0).split(raw)[0].strip(": ")
        yield DetectionResult(
            label=LABEL, text=raw, start=span[0], end=span[1],
            risk_level=RiskLevel.HIGH, confidence=0.9,
            evidence=["pattern:account", f"keyword:bank({bank})", "position:before"],
            legal_basis=LEGAL_BASIS,
            extra={"digits": digits, "length": len(digits),
                   "bank": bank, "category": CATEGORY},
        )

    # 3) 은행명 anchor (뒤)
    for m in _BANK_AFTER_PATTERN.finditer(text):
        raw = m.group(1).rstrip()
        digits = _normalize_and_check(raw)
        if digits is None:
            continue
        span = (m.start(1), m.start(1) + len(raw))
        if span in seen or any(s < span[1] and span[0] < e for s, e in seen):
            continue
        seen.add(span)
        bank = m.group(0).split(raw)[-1].strip(": ")
        yield DetectionResult(
            label=LABEL, text=raw, start=span[0], end=span[1],
            risk_level=RiskLevel.HIGH, confidence=0.9,
            evidence=["pattern:account", f"keyword:bank({bank})", "position:after"],
            legal_basis=LEGAL_BASIS,
            extra={"digits": digits, "length": len(digits),
                   "bank": bank, "category": CATEGORY},
        )
