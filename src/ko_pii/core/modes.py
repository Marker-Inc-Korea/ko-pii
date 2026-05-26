"""처리 모드 (Processing modes) — 사용자가 선택하는 차단 임계값.

각 모드는 "어느 수준의 위험을 차단/검토 대상으로 볼 것인가" 를 정의한다.
``Anonymizer`` 가 이 정책을 읽어 검출 결과를 처리한다.

| 모드        | 차단 임계 (위험도) | 차단 임계 (신뢰도) | 비고 |
|-------------|--------------------|--------------------|------|
| PARANOID    | LOW                | 0.5                | 가능한 모든 의심 PII 처리 |
| STRICT      | MEDIUM             | 0.7                | 기본 운영용 권장 |
| BALANCED    | HIGH               | 0.8                | FP 최소화 |
| PERMISSIVE  | CRITICAL           | 0.95               | 확정적 PII만 |
| AUDIT       | INFO               | 0.0                | 차단 안 함, 보고만 |
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ko_pii.core.types import RiskLevel


class ProcessingMode(str, Enum):
    PARANOID = "PARANOID"
    STRICT = "STRICT"
    BALANCED = "BALANCED"
    PERMISSIVE = "PERMISSIVE"
    AUDIT = "AUDIT"


class Action(str, Enum):
    BLOCK = "BLOCK"     # 본문에서 치환/마스킹
    REVIEW = "REVIEW"   # 검토 대상 (수동 확인 권장)
    ALLOW = "ALLOW"     # 통과


@dataclass(frozen=True)
class ModePolicy:
    mode: ProcessingMode
    block_risk_min: RiskLevel
    block_confidence_min: float
    review_risk_min: RiskLevel
    review_confidence_min: float

    def decide(self, risk: RiskLevel, confidence: float) -> Action:
        if self.mode == ProcessingMode.AUDIT:
            return Action.ALLOW
        if (
            int(risk) >= int(self.block_risk_min)
            and confidence >= self.block_confidence_min
        ):
            return Action.BLOCK
        if (
            int(risk) >= int(self.review_risk_min)
            and confidence >= self.review_confidence_min
        ):
            return Action.REVIEW
        return Action.ALLOW


_POLICIES: dict[ProcessingMode, ModePolicy] = {
    ProcessingMode.PARANOID: ModePolicy(
        mode=ProcessingMode.PARANOID,
        block_risk_min=RiskLevel.LOW,
        block_confidence_min=0.5,
        review_risk_min=RiskLevel.INFO,
        review_confidence_min=0.0,
    ),
    ProcessingMode.STRICT: ModePolicy(
        mode=ProcessingMode.STRICT,
        block_risk_min=RiskLevel.MEDIUM,
        block_confidence_min=0.7,
        review_risk_min=RiskLevel.LOW,
        review_confidence_min=0.5,
    ),
    ProcessingMode.BALANCED: ModePolicy(
        mode=ProcessingMode.BALANCED,
        block_risk_min=RiskLevel.HIGH,
        block_confidence_min=0.8,
        review_risk_min=RiskLevel.MEDIUM,
        review_confidence_min=0.6,
    ),
    ProcessingMode.PERMISSIVE: ModePolicy(
        mode=ProcessingMode.PERMISSIVE,
        block_risk_min=RiskLevel.CRITICAL,
        block_confidence_min=0.95,
        review_risk_min=RiskLevel.HIGH,
        review_confidence_min=0.7,
    ),
    ProcessingMode.AUDIT: ModePolicy(
        mode=ProcessingMode.AUDIT,
        block_risk_min=RiskLevel.CRITICAL,
        block_confidence_min=1.01,  # never block
        review_risk_min=RiskLevel.INFO,
        review_confidence_min=0.0,
    ),
}


def policy_for(mode: ProcessingMode) -> ModePolicy:
    return _POLICIES[mode]
