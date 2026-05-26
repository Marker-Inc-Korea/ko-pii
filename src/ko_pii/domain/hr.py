"""인사 도메인 — 사번·직번 등 내부 식별자.

추가 검출:
- 공무원/직원 사번 — "사번"/"공무원번호"/"직원번호"/"임용번호" 가 *숫자 직전에*
  콜론(:) 또는 공백을 사이에 두고 위치할 때만 매칭. 일반 문장
  ("이것은 사번이 다르다 ... 20240001") 에서 FP 가 나지 않도록 *tight anchor*.

공무원 직책 사전 세분화는 사용자 도메인 입력이 필요해
별도 기능으로 분리. 본 모듈은 키워드 anchor 기반 단순 룰.

Legal basis: 개인정보보호법 제2조; 국가공무원법 제22조.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "EMPLOYEE_ID"
LEGAL_BASIS = "개인정보보호법 제2조; 국가공무원법 제22조"
CATEGORY = "일반개인정보"

# FP 위험으로 제거된 키워드:
#   - "교번" : 수학·공학의 "교차/교번" 의미 충돌
_KEYWORDS = ("사번", "공무원번호", "직원번호", "임용번호", "사원번호")

# 키워드가 *숫자 직전에* (콜론·전각콜론·공백 옵션) 위치해야만 매칭.
_ANCHOR = re.compile(
    r"(?:" + "|".join(map(re.escape, _KEYWORDS)) + r")\s*[:：]?\s*$"
)

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{4,12})"
    r"(?![0-9])"
)


def _keyword_directly_before(text: str, start: int, window: int = 20) -> str | None:
    head = text[max(0, start - window): start]
    m = _ANCHOR.search(head)
    if m:
        return m.group(0).rstrip(" :：").strip()
    return None


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        kw = _keyword_directly_before(text, m.start())
        if kw is None:
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.85,
            evidence=["pattern:employee_id", f"keyword:{kw}", "domain:hr"],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "domain": "hr",
                "value": m.group(1),
            },
        )
