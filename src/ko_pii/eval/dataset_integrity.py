"""평가 데이터 무결성 가드 — train/test 누수 차단.

PII 데이터셋을 재분할(merge→reshuffle)하면 원본 파티션이 해체돼 **train 에 test 문장이
섞여 들어가는 누수**가 발생할 수 있다(예: 분류기 학습셋이 룰 벤치마크 test 코퍼스를 외움).
데이터 빌더는 분할 직후 ``assert_no_text_leakage`` 로 train∩test = ∅ 를 단언해야 한다.

권장: 원본 train/valid/test 파티션을 **그대로 보존**하고(재분할 X), 부득이 재분할 시
문장 단위 교집합이 0 임을 빌드 타임에 검증한다.
"""
from __future__ import annotations

import re
from typing import Iterable


def _norm(t: str) -> str:
    """공백 정규화 후 비교 키 — 사소한 공백 차이로 누수를 놓치지 않도록."""
    return re.sub(r"\s+", " ", (t or "")).strip()


def assert_no_text_leakage(
    train_texts: Iterable[str],
    test_texts: Iterable[str],
    *,
    name: str = "dataset",
) -> None:
    """train 과 test 의 (정규화된) 문장 교집합이 비어있지 않으면 AssertionError.

    Raises
    ------
    AssertionError — 누수된 문장 개수와 예시를 포함한 메시지.
    """
    tr = {_norm(t) for t in train_texts if _norm(t)}
    te = {_norm(t) for t in test_texts if _norm(t)}
    leaked = tr & te
    if leaked:
        sample = list(leaked)[:3]
        raise AssertionError(
            f"[{name}] train↔test 문장 누수 {len(leaked)}건 — "
            f"train 이 test 코퍼스를 외워 평가가 오염됨. 예: {sample}"
        )


def text_leakage_count(train_texts: Iterable[str], test_texts: Iterable[str]) -> int:
    """누수 문장 수만 반환 (assert 없이 점검용)."""
    tr = {_norm(t) for t in train_texts if _norm(t)}
    te = {_norm(t) for t in test_texts if _norm(t)}
    return len(tr & te)
