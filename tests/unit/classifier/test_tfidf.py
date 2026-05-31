"""TF-IDF 베이스라인 분류기 smoke test."""
import pickle
from pathlib import Path

import pytest

TFIDF_PATH = Path("models/pii_tfidf_v2.pkl")
if not TFIDF_PATH.exists():
    pytest.skip(
        f"TF-IDF 모델 없음: {TFIDF_PATH}. "
        f"python -m ko_pii.classifier.tfidf_baseline --data-dir data/classifier_clean "
        f"--output models/pii_tfidf_v2.pkl 먼저.",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def tfidf_bundle():
    with TFIDF_PATH.open("rb") as f:
        return pickle.load(f)


def test_bundle_contents(tfidf_bundle):
    assert "vectorizer" in tfidf_bundle
    assert "model" in tfidf_bundle


def test_predict_pii(tfidf_bundle):
    vec, model = tfidf_bundle["vectorizer"], tfidf_bundle["model"]
    X = vec.transform(["환경부 김도현 사무관 02-2110-6543"])
    prob = model.predict_proba(X)[0, 1]
    assert prob >= 0.5


def test_predict_no_pii(tfidf_bundle):
    vec, model = tfidf_bundle["vectorizer"], tfidf_bundle["model"]
    # 명확히 PII 없는 짧은 인사 (TF-IDF 모델이 false positive 가 많은 한계 인지)
    X = vec.transform(["좋은 하루 보내세요"])
    prob = model.predict_proba(X)[0, 1]
    assert prob < 0.5


def test_predict_batch(tfidf_bundle):
    vec, model = tfidf_bundle["vectorizer"], tfidf_bundle["model"]
    X = vec.transform([
        "주민등록번호 850729-2123456",
        "내일 보자",
        "이메일 hello@example.com",
    ])
    probs = model.predict_proba(X)[:, 1]
    assert probs[0] >= 0.5
    assert probs[2] >= 0.5
