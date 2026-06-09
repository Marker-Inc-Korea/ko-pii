"""데이터 무결성 가드 테스트 + KDPII 원본 파티션 무누수 확인."""
import json
from pathlib import Path

import pytest

from ko_pii.eval.dataset_integrity import assert_no_text_leakage, text_leakage_count


def test_detects_leakage():
    with pytest.raises(AssertionError):
        assert_no_text_leakage(["a", "b", "공유문장"], ["공유문장", "c"])


def test_clean_passes():
    assert_no_text_leakage(["a", "b"], ["c", "d"])  # raise 없음


def test_count():
    assert text_leakage_count(["a", "b", "x"], ["x", "y"]) == 1
    assert text_leakage_count(["a"], ["b"]) == 0


def test_whitespace_normalized():
    # 사소한 공백 차이로 누수를 놓치지 않아야
    with pytest.raises(AssertionError):
        assert_no_text_leakage(["hello  world"], ["hello world"])


def test_kdpii_original_pii_leakage_negligible():
    """KDPII 원본 train/test 의 *PII 보유* 중복 문장이 무시 가능해야 (NER 학습이 쓴 분할).

    KDPII 원본엔 짧은 공통 발화('네, 가능합니다.' 등) ~71개가 train/test 양쪽에 있으나
    PII 보유는 1개뿐 → 사실상 무누수. 반면 분류기 데이터를 merge→reshuffle 하면 1,000+
    문장이 누수되므로(감사 지적), 빌더는 원본 파티션 보존 + assert_no_text_leakage 로 차단.
    """
    kd = Path(__file__).resolve().parents[3] / "data" / "kdpii"
    if not (kd / "train.json").exists():
        pytest.skip("KDPII 데이터 없음")
    train = json.load(open(kd / "train.json", encoding="utf-8"))
    test = json.load(open(kd / "test.json", encoding="utf-8"))
    tr_pii = [d["sentence"] for d in train if d.get("PII_set")]
    te_pii = [d["sentence"] for d in test if d.get("PII_set")]
    assert text_leakage_count(tr_pii, te_pii) <= 5  # PII 보유 누수 무시 가능
