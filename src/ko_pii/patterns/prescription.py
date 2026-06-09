"""처방전 발행번호 (Prescription Issuance Number) detection — 식의약 도메인.

표준 (HIRA / 건강보험심사평가원 EMR 표준프레임워크):
- **처방전 발행번호 (처방전교부번호)**: 12자리 = ``YYYYMMDD`` (8) + 일련번호 (4)
  - 예: ``201912010001`` (2019.12.01 발행 1번)
- **의료기관기호**: 8자리 — HIRA 표준 의료기관 식별번호
  (처방전 자체보다 *발급기관* 식별이라 별도 PII 처리)

검출 정책:
- 12자리 처방번호는 단독으로는 거대 FP 위험 → **키워드 anchor** 필수
- 키워드: "처방번호", "처방전번호", "처방전 번호", "처방전 발행번호", "Rx", "Rx 번호"
- 발행 날짜 부분이 *유효 날짜* 여야 함 (1990-01-01 ~ 2099-12-31)
- 통상 의료기관기호 (8자리) 도 같은 anchor 로 emit

법적 근거:
- 의료법 제18조 (처방전 작성과 교부)
- 약사법 제22조 (조제내역 기록)
- 개인정보보호법 제23조 (민감정보 — 건강 정보)

위험도: HIGH (건강 정보 결합 → 민감속성).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PRESCRIPTION_ID"
LEGAL_BASIS = "의료법 제18조; 약사법 제22조; 개인정보보호법 제23조"
CATEGORY = "민감정보(건강)"

_KEYWORDS = (
    "처방번호", "처방전번호", "처방전 번호", "처방전 발행번호",
    "처방전교부번호", "교부번호",
    "Rx 번호", "Rx번호", "Rx",
)

# 처방전 발행번호: 12자리 = 날짜 8 + 일련 4
_ISSUANCE_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{4})(\d{2})(\d{2})(\d{4})"   # YYYY MM DD NNNN
    r"(?![0-9])"
)

# 의료기관기호: 8자리 (HIRA 표준) — anchor 필수
_INSTITUTION_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{8})"
    r"(?![0-9])"
)

_INSTITUTION_KEYWORDS = (
    "의료기관기호", "기관기호", "요양기관기호", "요양기관번호", "병원코드",
)

# 영문 접두 처방번호 (EMR 시스템별 다양): RX-2026-008471, PRSC-2026-0053-77192,
# RX-260503-44120 등. 키워드 anchor 가 필수라 영문+하이픈 ID 를 넓게 캡처해도 FP 안전.
_LABELED_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z]{2,6}-[0-9][0-9A-Za-z-]{3,22})(?![A-Za-z0-9])"
)


def _has_keyword_before(
    text: str, start: int, window: int, keywords: tuple[str, ...],
) -> str | None:
    head = text[max(0, start - window): start]
    for kw in keywords:
        if kw in head:
            return kw
    return None


def _is_valid_issuance_date(yyyy: str, mm: str, dd: str) -> bool:
    try:
        y, m, d = int(yyyy), int(mm), int(dd)
    except ValueError:
        return False
    if y < 1990 or y > 2099:
        return False
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    # 처방전 발행번호 (12자리)
    for m in _ISSUANCE_PATTERN.finditer(text):
        if not _is_valid_issuance_date(m.group(1), m.group(2), m.group(3)):
            continue
        kw = _has_keyword_before(text, m.start(), 20, _KEYWORDS)
        if kw is None:
            continue
        span = (m.start(), m.end())
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.HIGH,
            confidence=0.9,
            evidence=[
                "pattern:prescription_issuance",
                f"keyword:{kw}",
                f"date_valid:{m.group(1)}-{m.group(2)}-{m.group(3)}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "subtype": "issuance_id",
                "issue_date": f"{m.group(1)}-{m.group(2)}-{m.group(3)}",
                "serial": m.group(4),
            },
        )

    # 영문 접두 처방번호 (RX-/PRSC- 등) — 키워드 anchor 필수
    for m in _LABELED_ID_PATTERN.finditer(text):
        span = (m.start(1), m.end(1))
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        kw = _has_keyword_before(text, m.start(1), 18, _KEYWORDS)
        if kw is None:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(1),
            end=m.end(1),
            risk_level=RiskLevel.HIGH,
            confidence=0.88,
            evidence=["pattern:prescription_labeled_id", f"keyword:{kw}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": CATEGORY, "subtype": "labeled_id", "value": m.group(1)},
        )

    # 의료기관기호 (8자리, 별도 키워드)
    for m in _INSTITUTION_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        kw = _has_keyword_before(text, m.start(), 15, _INSTITUTION_KEYWORDS)
        if kw is None:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.85,
            evidence=[
                "pattern:prescription_institution",
                f"keyword:{kw}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "subtype": "institution_id",
                "value": m.group(1),
            },
        )
