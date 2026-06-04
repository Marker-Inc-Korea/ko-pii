"""신용카드 / 체크카드 번호 (Card Number) detection.

Detection requires the Luhn (mod-10) checksum to pass + IIN/BIN 첫 자리가
실제 카드 브랜드의 화이트리스트에 있어야 한다 (ISO/IEC 7812).

지원 BIN 첫 자리:
  3 - American Express, JCB, Diners Club
  4 - Visa
  5 - Mastercard
  6 - Discover / UnionPay
  9 - 한국 국내 전용 카드 (BC, 일부 백화점카드 등)
  2 - Mastercard 신규 BIN (2221~2720), 일부 한국 카드

거부: 0, 1, 7, 8 — 현행 카드 브랜드에 할당되지 않음.

Luhn 만으로는 "1111-2222-3333-4444" 같이 trivial 한 반복 숫자가 우연히
통과하여 FP 가 됨. 따라서 첫 자리 화이트리스트로 한 단계 더 거름.

Legal basis: 개인정보보호법 제2조; 여신전문금융업법.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.checksum.luhn import is_valid as is_valid_luhn
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "CARD"
LEGAL_BASIS = "개인정보보호법 제2조; 여신전문금융업법"
CATEGORY = "일반개인정보"

_VALID_BIN_FIRST_DIGITS: frozenset[str] = frozenset({"2", "3", "4", "5", "6", "9"})

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(?:"
    r"[0-9]{4}[-. /]\s?[0-9]{4}[-. /]\s?[0-9]{4}[-. /]\s?[0-9]{1,7}"
    r"|"
    r"[0-9]{13,19}"
    r")"
    r"(?![0-9])"
)


def _brand_for(first_digit: str) -> str:
    return {
        "3": "amex_or_jcb_or_diners",
        "4": "visa",
        "5": "mastercard",
        "6": "discover_or_unionpay",
        "9": "korea_domestic",
        "2": "mastercard_new_or_misc",
    }.get(first_digit, "unknown")


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        raw = m.group(0)
        digits = re.sub(r"\D", "", raw)
        if not (13 <= len(digits) <= 19):
            continue
        if digits[0] not in _VALID_BIN_FIRST_DIGITS:
            continue
        if not is_valid_luhn(digits):
            continue
        yield DetectionResult(
            label=LABEL,
            text=raw,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.HIGH,
            confidence=1.0,
            evidence=[
                "pattern:card",
                "checksum:luhn_valid",
                f"brand_hint:{_brand_for(digits[0])}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "digits": digits,
                "length": len(digits),
                "brand_hint": _brand_for(digits[0]),
                "category": CATEGORY,
            },
        )
