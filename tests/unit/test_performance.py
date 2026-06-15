"""성능 회귀 가드 — detect_all 이 입력 길이에 선형이어야(quadratic 재발 방지).

과거 person detector 에 두 개의 O(n²) 가 있었다: (1) co-occurrence boost 가 후보마다
문장 단어를 재순회, (2) _DETERMINISTIC_HINTS 이메일 패턴이 긴 영숫자열에서 백트래킹.
둘 다 닫혔고, 이 테스트가 재발을 잡는다(보수적 상한이라 느린 CI 에서도 안전).
"""
from __future__ import annotations

import time

from ko_pii import detect_all


def _elapsed(text: str) -> float:
    start = time.perf_counter()
    detect_all(text)
    return time.perf_counter() - start


def test_long_digit_string_is_linear() -> None:
    # 이메일 hint 백트래킹 회귀 시 수십 초가 걸린다 → 2s 상한.
    assert _elapsed("1" * 100_000) < 2.0


def test_name_heavy_text_is_linear() -> None:
    # co-occurrence boost 의 문장-단어 재순회 회귀 시 quadratic.
    assert _elapsed("환경부 김도현 사무관 회의 결과 " * 4_000) < 2.0


def test_scaling_stays_sub_quadratic() -> None:
    # 입력 4배 → 시간이 8배(=2x linear margin) 를 넘으면 quadratic 의심.
    small = _elapsed("김철수 " * 4_000)
    large = _elapsed("김철수 " * 16_000)
    if small > 0.005:  # 측정 잡음 회피
        assert large < small * 8, f"super-linear scaling: {small:.3f}s -> {large:.3f}s"


def test_double_pass_gated_by_alnum_shape() -> None:
    # 원본 재검사(더블패스)는 invisible 제거가 '영숫자 런 모양'을 바꾼 경우만 — 한글/공백
    # 사이 제로폭 떡칠은 모양 불변이라 단일 패스(제로폭 1자 2x DoS 완화).
    from ko_pii.detect import _run_shape
    assert _run_shape("900101 1234567") != _run_shape("9001011234567")  # 영숫자 융합 → 더블
    assert _run_shape("가나다 라마바") == _run_shape("가나다라마바")      # 한글 → 단일
    assert _run_shape("안녕 하세요 반갑") == _run_shape("안녕하세요반갑")
