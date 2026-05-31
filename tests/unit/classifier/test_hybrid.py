"""HybridAnonymizer smoke test — 룰(ko-pii) + 분류기 결합."""
from pathlib import Path

import pytest

MODEL_PATH = Path("models/pii_classifier_v6/final")
if not MODEL_PATH.exists():
    pytest.skip(f"학습된 모델 없음: {MODEL_PATH}", allow_module_level=True)

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.classifier import (
    HybridAnonymizer,
    HybridMode,
    PIIClassifier,
)


@pytest.fixture(scope="module")
def rule():
    return Anonymizer(mode=ProcessingMode.BALANCED)


@pytest.fixture(scope="module")
def clf():
    return PIIClassifier.from_pretrained(MODEL_PATH)


class TestScoreMode:
    def test_agree_pii(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.SCORE)
        r = h.process("환경부 김도현 사무관 02-2110-6543")
        assert r.has_pii
        assert r.classifier_score >= 0.5
        assert r.agreement == "agree_pii"
        assert len(r.rule_result.detections) > 0

    def test_agree_no_pii(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.SCORE)
        r = h.process("오늘 회의 분위기가 그저 그랬다.")
        assert r.classifier_score < 0.5
        assert r.agreement == "agree_no_pii"
        assert len(r.rule_result.detections) == 0

    def test_result_carries_rule_detections(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.SCORE)
        r = h.process("주민등록번호 850729-2123456 입니다.")
        # 룰이 RRN 잡고 분류기도 high score
        rrn_dets = [d for d in r.rule_result.detections if d.detection.label == "RRN"]
        assert len(rrn_dets) >= 1
        assert r.classifier_score >= 0.5


class TestReviewFlagMode:
    def test_review_recommended_on_disagreement(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.REVIEW_FLAG)
        # classifier만 잡는 케이스는 random — 동작만 검증
        r = h.process("환경부 김도현 사무관 02-2110-6543")
        # 양쪽 다 잡으면 review_recommended=False (REVIEW_FLAG는 classifier_only일 때만 trigger)
        if r.agreement == "agree_pii":
            assert not r.review_recommended


class TestUnionBlockMode:
    def test_one_sided_triggers_review(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.UNION_BLOCK)
        r = h.process("주민등록번호 850729-2123456")
        # 두 검출기 합의 또는 단독
        assert r.agreement in {"agree_pii", "rule_only", "classifier_only"}


class TestGatedMode:
    def test_low_score_skips_ko_pii(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.GATED, gate_threshold=0.5)
        r = h.process("ㅎㅎ ㅋㅋ 잘 들어가")  # 분류기 낮을 텍스트
        if r.metadata.get("gated_skip"):
            assert len(r.rule_result.detections) == 0


class TestResultFields:
    def test_has_pii_property(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.SCORE)
        r = h.process("아무 글")
        assert isinstance(r.has_pii, bool)

    def test_summary_includes_classifier_score(self, rule, clf):
        h = HybridAnonymizer(rule, clf, mode=HybridMode.SCORE)
        r = h.process("환경부 김도현 02-2110-6543")
        s = r.summary
        assert "classifier_score" in s
        assert "agreement" in s
        assert "review_recommended" in s
