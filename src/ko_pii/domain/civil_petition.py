"""민원 응대 문서 도메인 — 민원번호 + 신청서 번호.

추가 검출:
- 민원번호 (예: ``2024-민원-00123``) — 민원 통합관리시스템 표준
- 정보공개 청구번호 (예: ``정보공개-2024-00567``)

이름·전화·이메일 등 핵심 PII 는 기본 검출기에서 이미 잡음.

Legal basis: 개인정보보호법 제2조, 「민원처리에 관한 법률」 제3조.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PETITION_ID"
LEGAL_BASIS = "개인정보보호법 제2조; 민원처리에 관한 법률"
CATEGORY = "참조정보"

_PATTERN = re.compile(
    r"(?<![A-Za-z0-9가-힣])"
    r"("
    r"(?:19|20)\d{2}"      # 연도 (앞)
    r"-"
    r"(?:민원|정보공개|이의신청|행정심판)"
    r"-"
    r"\d{4,8}"             # 일련번호
    r"|"
    r"(?:민원|정보공개|이의신청|행정심판)"  # 또는 키워드 (앞)
    r"-"
    r"(?:19|20)\d{2}"
    r"-"
    r"\d{4,8}"
    r")"
    r"(?![A-Za-z0-9가-힣])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            evidence=["pattern:petition_id", "domain:civil_petition"],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                "domain": "civil_petition",
            },
        )
