"""건강보험증 번호 (National Health Insurance Card Number) detection.

11-digit identifier issued by 국민건강보험공단. Because plain 11-digit numeric
runs collide heavily with mobile phone numbers and other identifiers, this
detector requires a context keyword (건강보험 / 의료보험 / 보험증) within ~25
characters before the candidate — tight enough to exclude paragraph-level
mentions, wide enough to allow ":" / linebreak / brief noun between them.

Risk: HIGH. While the number itself is not classified as 민감정보, it is a
direct entry point to medical-claim history and should be treated as a
high-sensitivity personal identifier.

Legal basis: 개인정보보호법 제2조; 국민건강보험법 제96조 (자료의 보호).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "MEDICAL_INSURANCE"
LEGAL_BASIS = "개인정보보호법 제2조; 국민건강보험법 제96조"
CATEGORY = "일반개인정보"

_CONTEXT_WINDOW = 25
_KEYWORD_RE = re.compile(r"건강\s*보험|의료\s*보험|보험증")
# 건강보험증번호 형식 2종: 순수 11자리, 또는 '증번호' 표기형 N-NNNNNNNNNN
# (1자리 종별 코드 + 하이픈 + 10자리). 키워드 anchor 가 있어 FP 위험은 낮다.
_NUMBER_RE = re.compile(r"(?<![0-9-])((?:[0-9]-[0-9]{10})|(?:[0-9]{11}))(?![0-9-])")


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _NUMBER_RE.finditer(text):
        window_start = max(0, m.start() - _CONTEXT_WINDOW)
        prefix_window = text[window_start:m.start()]
        if not _KEYWORD_RE.search(prefix_window):
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(1),
            start=m.start(1),
            end=m.end(1),
            risk_level=RiskLevel.HIGH,
            confidence=0.9,
            evidence=["pattern:medical_insurance", "context:keyword_found"],
            legal_basis=LEGAL_BASIS,
            extra={
                "digits": m.group(1),
                "category": CATEGORY,
            },
        )
