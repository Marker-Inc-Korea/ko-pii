"""사업자등록번호 (Business Registration Number) detection.

10-digit format: XXX-XX-XXXXX, optional hyphens.

Legal status: 사업자등록번호 자체는 법인의 경우 개인정보로 보기 어렵지만,
개인사업자의 경우 사업자등록번호가 곧 개인을 식별하는 정보가 됨 → 보수적으로
HIGH 위험도로 보고. 후속 도메인 규칙에서 사업체 유형에 따라 조정 가능.

Detection requires the 국세청 checksum to pass — short numeric runs that
happen to match the 3-2-5 pattern but fail the checksum are filtered out.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.checksum.business_reg_checksum import is_valid_checksum
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "BUSINESS_REG"
LEGAL_BASIS = "개인정보보호법 제2조 (개인사업자의 경우 개인 식별 정보)"
CATEGORY = "일반개인정보"

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{3})-?"
    r"([0-9]{2})-?"
    r"([0-9]{5})"
    r"(?![0-9])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        digits = m.group(1) + m.group(2) + m.group(3)
        # 모두 0 인 placeholder 거부 (체크섬 통과해도 실제 사업자 아님)
        if digits == "0000000000":
            continue
        if not is_valid_checksum(digits):
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.HIGH,
            confidence=1.0,
            evidence=["pattern:business_reg", "checksum:valid"],
            legal_basis=LEGAL_BASIS,
            extra={
                "digits": digits,
                "checksum_valid": True,
                "category": CATEGORY,
            },
        )
