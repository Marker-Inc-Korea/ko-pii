"""Analytics — 검출 결과의 *조합* 위험도 평가 및 k-익명성 검증.

개인정보보호위원회 「개인정보 비식별 조치 가이드라인」 직접 대응:
- 식별자 / 준식별자 / 민감속성 / 일반속성 분류
- 결합 위험도 (combined risk) 자동 계산
- k-익명성 / l-다양성 / t-근접성 평가
"""
from ko_pii.analytics.combined_risk import (
    Identifier, AttributeClass,
    classify_attribute, score_combined_risk,
    CombinedRiskReport,
)
from ko_pii.analytics.k_anonymity import (
    k_anonymity, evaluate_dataset,
    KAnonymityReport,
)

__all__ = [
    "Identifier", "AttributeClass",
    "classify_attribute", "score_combined_risk",
    "CombinedRiskReport",
    "k_anonymity", "evaluate_dataset",
    "KAnonymityReport",
]
