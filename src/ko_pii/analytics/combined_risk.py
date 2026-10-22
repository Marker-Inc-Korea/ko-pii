"""선택된 탐지 라벨의 조합을 집계하는 위험도 휴리스틱.

라벨 분류와 수치 기준은 이 라이브러리의 처리 정책이다. 실제 개인의 식별 가능성,
법적 익명성 또는 개인정보 부재를 판정하지 않는다. 누락된 탐지는 평가할 수 없다.
준식별자 종류 0~1개는 LOW, 2~3개는 MEDIUM, 4개 이상은 HIGH로 집계한다.
식별자 라벨이 있으면 CRITICAL, 민감속성 라벨은 한 단계 가산한다.
처리 모드의 차단 여부는 별도로 결정된다.
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


# Library policy categories, not a legal classification of each source value.
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
        """Observed-label heuristic is HIGH/CRITICAL, not an identifiability proof."""
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
            f"선택된 탐지에서 식별자 {len(ids)}종 관측: {', '.join(sorted(ids))} → 규칙상 CRITICAL"
        )
    elif len(quasi) >= 4:
        rpt.combined_risk = RiskLevel.HIGH
        rpt.rationale.append(
            f"준식별자 {len(quasi)}종 관측 → 규칙상 HIGH "
            f"({', '.join(sorted(quasi))})"
        )
    elif len(quasi) >= 2:
        rpt.combined_risk = RiskLevel.MEDIUM
        rpt.rationale.append(
            f"준식별자 {len(quasi)}종 결합 → 재식별 가능성 있음"
        )
    elif len(quasi) == 1:
        rpt.combined_risk = RiskLevel.LOW
        rpt.rationale.append("준식별자 1종 관측 → 규칙상 LOW; 단독 식별 불가를 뜻하지 않음")
    else:
        rpt.combined_risk = RiskLevel.INFO
        rpt.rationale.append("선택된 탐지 결과에서 식별자/준식별자 라벨을 찾지 못함; 원문에 없다는 보장은 아님")

    # 민감속성 등장 시 한 단계 가산 (CRITICAL 캡)
    if sensitive and rpt.combined_risk < RiskLevel.CRITICAL:
        prev = rpt.combined_risk
        rpt.combined_risk = RiskLevel(min(int(prev) + 1, int(RiskLevel.CRITICAL)))
        rpt.rationale.append(
            f"민감속성 {len(sensitive)}종 등장 ({', '.join(sorted(sensitive))}) "
            f"→ 위험도 {prev.name} → {rpt.combined_risk.name}"
        )

    return rpt
