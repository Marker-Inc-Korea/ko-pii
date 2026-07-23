"""국적/국가명 (Nationality) detection — ADDRESS 에서 분리.

"거주지국 대한민국", "국적 미국", "한국인" 등 국가명은 주소가 아니라 국적 정보.
ADDRESS 카테고리와 혼동 방지를 위해 별도 검출기로 분리.

Legal basis: 개인정보보호법 제2조 (국적은 준식별자로 분류 가능).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.dictionaries.districts import is_country

LABEL = "NATIONALITY"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "준식별자"

# 단독 토큰 매칭 — 앞뒤 한글/영숫자 거부
_PATTERN_TOKEN = re.compile(
    r"(?<![가-힣A-Za-z0-9])([가-힣]{2,8})(?![가-힣A-Za-z0-9])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    """Yield DetectionResult for each country/nationality mention."""
    from ko_pii.context.particles import strip_trailing_particle

    for m in _PATTERN_TOKEN.finditer(text):
        raw_token = m.group(1)
        token, particle = strip_trailing_particle(raw_token)
        if len(token) < 2:
            continue

        # "한국인/미국인" → "한국/미국"
        people_suffix = None
        if len(token) >= 3 and token.endswith("인") and is_country(token[:-1]):
            token = token[:-1]
            people_suffix = "인"

        if not is_country(token):
            continue

        actual_end = m.end() - (len(particle) if particle else 0) - (1 if people_suffix else 0)

        yield DetectionResult(
            label=LABEL,
            text=token,
            start=m.start(),
            end=actual_end,
            risk_level=RiskLevel.LOW,
            confidence=0.7,
            evidence=["pattern:nationality", "dict:country"],
            legal_basis=LEGAL_BASIS,
            extra={
                "country": token,
                "category": CATEGORY,
            },
        )
