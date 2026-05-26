"""EDI 약품코드 (식약처 의약품 표준코드) detection — 식의약 도메인.

표준 (식약처 / 의약품관리종합센터 KPIS):
- **EDI 코드**: 9자리 숫자 = 업체식별코드(4) + 품목코드(5)
- **KD 코드**: 13자리 숫자 = 국가식별(3) + 업체(4) + 품목(5) + 검증(1)

검출 정책:
- 9자리/13자리 단독 숫자는 FP 위험 큼 → **키워드 anchor 필수**
- 키워드: "EDI", "약품코드", "의약품코드", "주성분코드", "KD코드", "약가코드"

법적 근거: 약사법 제31조 (의약품 표준코드 관리), 개인정보보호법 제2조.

위험도: LOW (코드 자체는 PII 아니지만 처방·환자정보와 결합 시 가산).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "EDI_DRUG"
LEGAL_BASIS = "약사법 제31조; 개인정보보호법 제2조"
CATEGORY = "참조정보"

# 13자리 KD 코드 우선 (longer-first), 그 다음 9자리 EDI
_PATTERN_13 = re.compile(
    r"(?<![0-9])"
    r"(\d{13})"
    r"(?![0-9])"
)

_PATTERN_9 = re.compile(
    r"(?<![0-9])"
    r"(\d{9})"
    r"(?![0-9])"
)

# FP 위험으로 제거된 키워드:
#   - "표준코드" : 일반 산업·제품 표준 코드와 충돌 (의약품 한정 단서 부족)
_KEYWORDS = (
    "EDI", "edi",
    "약품코드", "의약품코드", "주성분코드",
    "KD코드", "KD 코드", "약가코드",
)


def _has_keyword_before(text: str, start: int, window: int = 18) -> str | None:
    head = text[max(0, start - window): start]
    for kw in _KEYWORDS:
        if kw in head:
            return kw
    return None


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    for m in _PATTERN_13.finditer(text):
        kw = _has_keyword_before(text, m.start())
        if kw is None:
            continue
        digits = m.group(1)
        # 첫 3자리 국가식별코드는 한국이 880~881 (대한상의 유통물류진흥원)
        if not digits.startswith(("880", "881", "888")):
            continue
        span = (m.start(), m.end())
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=digits,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            evidence=[
                "pattern:edi_drug",
                "format:kd_code_13",
                f"keyword:{kw}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "format": "kd_code_13",
                "country_id": digits[0:3],
                "company_id": digits[3:7],
                "item_id": digits[7:12],
                "check_digit": digits[12],
            },
        )

    for m in _PATTERN_9.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        kw = _has_keyword_before(text, m.start())
        if kw is None:
            continue
        seen.add(span)
        digits = m.group(1)
        yield DetectionResult(
            label=LABEL,
            text=digits,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            evidence=["pattern:edi_drug", "format:edi_9", f"keyword:{kw}"],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "format": "edi_9",
                "company_id": digits[0:4],
                "item_id": digits[4:9],
            },
        )
