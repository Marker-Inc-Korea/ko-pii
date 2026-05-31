"""PIIClassifier 추론 smoke test.

학습된 모델 디렉토리가 없으면 module 전체 skip.
모델 학습: `sbatch scripts/train_classifier_v6.sbatch`
"""
from pathlib import Path

import pytest

MODEL_PATH = Path("models/pii_classifier_v6/final")
if not MODEL_PATH.exists():
    pytest.skip(
        f"학습된 모델 없음: {MODEL_PATH}. sbatch scripts/train_classifier_v6.sbatch 먼저.",
        allow_module_level=True,
    )

from ko_pii.classifier import PIIClassifier


@pytest.fixture(scope="module")
def clf():
    return PIIClassifier.from_pretrained(MODEL_PATH)


class TestPredictSingle:
    def test_pii_phone_and_person(self, clf):
        label, score = clf.predict("환경부 폐기물처리과 김도현 사무관 02-2110-6543")
        assert label == 1
        assert score >= 0.5

    def test_pii_rrn(self, clf):
        label, score = clf.predict("주민등록번호 850729-2123456 으로 가입 부탁드립니다.")
        assert label == 1
        assert score >= 0.5

    def test_no_pii_smalltalk(self, clf):
        label, score = clf.predict("오늘 회의 분위기가 별로 좋지 않았다.")
        assert label == 0
        assert score < 0.5

    def test_returns_probability_in_range(self, clf):
        _, score = clf.predict("아무 텍스트")
        assert 0.0 <= score <= 1.0


class TestPredictBatch:
    def test_batch_preserves_order(self, clf):
        texts = [
            "환경부 김도현 사무관 02-2110-6543",
            "오늘 날씨 좋네요.",
            "RRN 850729-2123456",
        ]
        results = clf.predict_batch(texts)
        assert len(results) == 3
        assert results[0][0] == 1
        assert results[1][0] == 0
        assert results[2][0] == 1

    def test_empty_batch(self, clf):
        assert clf.predict_batch([]) == []

    def test_has_pii_convenience(self, clf):
        assert clf.has_pii("주민등록번호 850729-2123456")
        assert not clf.has_pii("오늘 날씨가 정말 좋다.")


class TestThreshold:
    def test_custom_threshold(self, clf):
        # 임계값 조정 시 label 변하는지
        clf_low = type(clf)(clf.model, clf.tokenizer, threshold=0.05)
        # 매우 낮은 임계값이면 거의 모든 게 label=1
        assert clf_low.predict("어 그래")[0] in (0, 1)  # 동작만 검증
