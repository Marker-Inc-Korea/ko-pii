"""룰 (ko-pii Anonymizer) + ML (PIIClassifier) 하이브리드 검출기.

ko-pii 의 span-level 룰 결과 + 분류기의 문서-level confidence 를 조합.
분류기는 SecondaryDetector 프로토콜과 다른 추상 레벨 (문서/청크 binary)이라
별도 wrapper 로 제공.

운영 모드:
    SCORE       — ko-pii spans + classifier score 단순 보강 (가장 일반적)
    GATED       — classifier 점수 < threshold 면 ko-pii skip (속도 우선)
    REVIEW_FLAG — ko-pii 검출 0인데 classifier 높으면 'REVIEW' 메타 추가
    UNION_BLOCK — ko-pii OR classifier 한쪽이라도 PII 라 보면 BLOCK 처리
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ko_pii.anonymizer import Anonymizer, AnonymizationResult
from ko_pii.classifier.predict import PIIClassifier


class HybridMode(str, Enum):
    SCORE = "score"
    GATED = "gated"
    REVIEW_FLAG = "review_flag"
    UNION_BLOCK = "union_block"


@dataclass
class HybridResult:
    """ko-pii + 분류기 결합 결과."""

    text: str
    anonymized: str
    rule_result: AnonymizationResult
    classifier_score: float
    agreement: str  # 'agree_pii' / 'agree_no_pii' / 'rule_only' / 'classifier_only'
    review_recommended: bool = False
    metadata: dict = field(default_factory=dict)

    @property
    def has_pii(self) -> bool:
        return bool(self.rule_result.detections) or self.review_recommended

    @property
    def summary(self) -> dict:
        s = dict(self.rule_result.summary)
        s["classifier_score"] = self.classifier_score
        s["agreement"] = self.agreement
        s["review_recommended"] = self.review_recommended
        return s


class HybridAnonymizer:
    """룰(ko-pii) + ML(PIIClassifier) 하이브리드 검출기.

    Examples
    --------
    >>> from ko_pii import Anonymizer, ProcessingMode
    >>> from ko_pii.classifier import PIIClassifier
    >>> from ko_pii.classifier.hybrid import HybridAnonymizer, HybridMode
    >>>
    >>> rule = Anonymizer(mode=ProcessingMode.BALANCED)
    >>> clf  = PIIClassifier.from_pretrained("models/pii_classifier_v6/final")
    >>> hyb  = HybridAnonymizer(rule, clf, mode=HybridMode.REVIEW_FLAG)
    >>> r = hyb.process("환경부 김도현 사무관 02-2110-6543")
    >>> r.has_pii, r.classifier_score, r.agreement
    (True, 0.997, 'agree_pii')
    """

    def __init__(
        self,
        rule_detector: Anonymizer,
        classifier: PIIClassifier,
        *,
        mode: HybridMode = HybridMode.SCORE,
        classifier_threshold: float = 0.5,
        gate_threshold: float = 0.1,
    ):
        self.rule = rule_detector
        self.classifier = classifier
        self.mode = HybridMode(mode)
        self.classifier_threshold = classifier_threshold
        self.gate_threshold = gate_threshold

    def process(self, text: str) -> HybridResult:
        # 분류기 호출 (light)
        _, clf_score = self.classifier.predict(text)
        clf_positive = clf_score >= self.classifier_threshold

        # GATED: 분류기가 매우 낮은 점수면 ko-pii 호출 자체 skip
        if self.mode == HybridMode.GATED and clf_score < self.gate_threshold:
            empty = self.rule.__class__(  # 빈 Anonymizer 재호출은 비효율, mock 결과
                mode=self.rule.mode, strategy=self.rule.strategy
            ).process("")
            return HybridResult(
                text=text,
                anonymized=text,
                rule_result=empty,
                classifier_score=clf_score,
                agreement="agree_no_pii",
                review_recommended=False,
                metadata={"gated_skip": True, "threshold": self.gate_threshold},
            )

        # ko-pii 룰 실행
        rule_result = self.rule.process(text)
        rule_positive = bool(rule_result.detections)

        # 일치 상태 분류
        if rule_positive and clf_positive:
            agreement = "agree_pii"
        elif not rule_positive and not clf_positive:
            agreement = "agree_no_pii"
        elif rule_positive and not clf_positive:
            agreement = "rule_only"
        else:
            agreement = "classifier_only"

        review_recommended = False
        meta: dict = {}

        if self.mode == HybridMode.REVIEW_FLAG:
            # ko-pii 가 0인데 classifier 높음 → 사람 검토 권고
            if agreement == "classifier_only":
                review_recommended = True
                meta["flag_reason"] = (
                    f"분류기 확신도 {clf_score:.2f} 인데 룰 검출 0"
                )

        if self.mode == HybridMode.UNION_BLOCK:
            # 한쪽이라도 PII → BLOCK 처리 권고
            if agreement in {"classifier_only", "rule_only"}:
                review_recommended = True
                meta["flag_reason"] = f"한쪽만 검출 ({agreement})"

        return HybridResult(
            text=text,
            anonymized=rule_result.text,
            rule_result=rule_result,
            classifier_score=clf_score,
            agreement=agreement,
            review_recommended=review_recommended,
            metadata=meta,
        )
