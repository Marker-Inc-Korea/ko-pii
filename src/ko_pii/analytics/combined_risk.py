"""결합 위험도 평가 — 검출 결과의 조합이 *함께* 식별 가능한가.

「개인정보 비식별 조치 가이드라인」(개인정보보호위원회) 분류:
- **식별자 (identifier)**: 단독으로 개인 식별 가능. 무조건 차단.
- **준식별자 (quasi-identifier)**: 단독은 식별 불가하나, 결합 시 식별 가능.
- **민감속성 (sensitive attribute)**: 식별과는 별개로 보호 대상 정보.
- **일반속성 (general attribute)**: 위 셋에 해당하지 않음.

결합 위험도는 한 문서에 등장한 *서로 다른* 준식별자 종류의 수에 따라 증가:
- 0~1 종류: 위험 LOW
- 2~3 종류: 위험 MEDIUM (재식별 가능성 있음)
- 4 이상: 위험 HIGH (거의 확실히 재식별 가능)

식별자가 1개라도 있으면 자동 CRITICAL. 민감속성 등장 시 한 단계 가산.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from ko_pii.core.types import DetectionResult, RiskLevel


class AttributeClass(Enum):
    IDENTIFIER = "identifier"
    QUASI_IDENTIFIER = "quasi_identifier"
    SENSITIVE = "sensitive"
    GENERAL = "general"


# 라벨 → 속성 분류 매핑 (가이드라인 + 본 라이브러리 카테고리)
_LABEL_TO_CLASS: dict[str, AttributeClass] = {
    # 식별자 (단독 식별)
    "RRN": AttributeClass.IDENTIFIER,
    "FRN": AttributeClass.IDENTIFIER,
    "PASSPORT": AttributeClass.IDENTIFIER,
    "DRIVER_LICENSE": AttributeClass.IDENTIFIER,
    "CARD": AttributeClass.IDENTIFIER,
    # 준식별자 (결합 식별)
    "PERSON": AttributeClass.QUASI_IDENTIFIER,
    "PHONE": AttributeClass.QUASI_IDENTIFIER,
    "EMAIL": AttributeClass.QUASI_IDENTIFIER,
    "ADDRESS": AttributeClass.QUASI_IDENTIFIER,
    "POSTAL_CODE": AttributeClass.QUASI_IDENTIFIER,
    "ACCOUNT": AttributeClass.QUASI_IDENTIFIER,
    "BUSINESS_REG": AttributeClass.QUASI_IDENTIFIER,
    "CORP_REG": AttributeClass.QUASI_IDENTIFIER,
    "VEHICLE": AttributeClass.QUASI_IDENTIFIER,
    "EMPLOYEE_ID": AttributeClass.QUASI_IDENTIFIER,
    "IP": AttributeClass.QUASI_IDENTIFIER,
    # 인적 속성 (KDPII 준식별자)
    "DT_BIRTH": AttributeClass.QUASI_IDENTIFIER,
    "EDUCATION": AttributeClass.QUASI_IDENTIFIER,
    "MAJOR": AttributeClass.QUASI_IDENTIFIER,
    "POSITION": AttributeClass.QUASI_IDENTIFIER,
    "AGE": AttributeClass.QUASI_IDENTIFIER,
    "HEIGHT": AttributeClass.QUASI_IDENTIFIER,
    "WEIGHT": AttributeClass.QUASI_IDENTIFIER,
    # 민감속성 (보호 대상)
    "MEDICAL_INSURANCE": AttributeClass.SENSITIVE,
    "PRESCRIPTION_ID": AttributeClass.SENSITIVE,
    "COURT_CASE": AttributeClass.SENSITIVE,
    # 일반·참조
    "URL": AttributeClass.GENERAL,
    "FAX": AttributeClass.GENERAL,
    "DOC_ID": AttributeClass.GENERAL,
    "PETITION_ID": AttributeClass.GENERAL,
    "PNU": AttributeClass.GENERAL,
}


@dataclass
class Identifier:
    label: str
    text: str
    attribute_class: AttributeClass


@dataclass
class CombinedRiskReport:
    distinct_identifiers: list[str] = field(default_factory=list)
    distinct_quasi: list[str] = field(default_factory=list)
    sensitive_present: list[str] = field(default_factory=list)
    combined_risk: RiskLevel = RiskLevel.LOW
    rationale: list[str] = field(default_factory=list)

    def is_re_identifiable(self) -> bool:
        """True 이면 재식별 가능성이 충분 높음 (CRITICAL/HIGH)."""
        return self.combined_risk >= RiskLevel.HIGH


def classify_attribute(label: str) -> AttributeClass:
    return _LABEL_TO_CLASS.get(label, AttributeClass.GENERAL)


def score_combined_risk(
    detections: Iterable[DetectionResult],
) -> CombinedRiskReport:
    """주어진 검출 결과 집합의 *조합* 위험도를 산출."""
    rpt = CombinedRiskReport()

    ids: set[str] = set()
    quasi: set[str] = set()
    sensitive: set[str] = set()

    for d in detections:
        cls = classify_attribute(d.label)
        if cls == AttributeClass.IDENTIFIER:
            ids.add(d.label)
        elif cls == AttributeClass.QUASI_IDENTIFIER:
            quasi.add(d.label)
        elif cls == AttributeClass.SENSITIVE:
            sensitive.add(d.label)

    rpt.distinct_identifiers = sorted(ids)
    rpt.distinct_quasi = sorted(quasi)
    rpt.sensitive_present = sorted(sensitive)

    # 위험도 결정
    if ids:
        rpt.combined_risk = RiskLevel.CRITICAL
        rpt.rationale.append(
            f"식별자 {len(ids)}종 등장: {', '.join(sorted(ids))} → 즉시 식별 가능"
        )
    elif len(quasi) >= 4:
        rpt.combined_risk = RiskLevel.HIGH
        rpt.rationale.append(
            f"준식별자 {len(quasi)}종 결합 → 재식별 가능성 매우 높음 "
            f"({', '.join(sorted(quasi))})"
        )
    elif len(quasi) >= 2:
        rpt.combined_risk = RiskLevel.MEDIUM
        rpt.rationale.append(
            f"준식별자 {len(quasi)}종 결합 → 재식별 가능성 있음"
        )
    elif len(quasi) == 1:
        rpt.combined_risk = RiskLevel.LOW
        rpt.rationale.append("준식별자 1종 → 단독 식별 어려움")
    else:
        rpt.combined_risk = RiskLevel.INFO
        rpt.rationale.append("식별 정보 없음")

    # 민감속성 등장 시 한 단계 가산 (CRITICAL 캡)
    if sensitive and rpt.combined_risk < RiskLevel.CRITICAL:
        prev = rpt.combined_risk
        rpt.combined_risk = RiskLevel(min(int(prev) + 1, int(RiskLevel.CRITICAL)))
        rpt.rationale.append(
            f"민감속성 {len(sensitive)}종 등장 ({', '.join(sorted(sensitive))}) "
            f"→ 위험도 {prev.name} → {rpt.combined_risk.name}"
        )

    return rpt
