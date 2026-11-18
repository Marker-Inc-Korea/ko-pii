"""성능 회귀 가드 — detect_all 이 입력 길이에 선형이어야(quadratic 재발 방지).

과거 person detector 에 두 개의 O(n²) 가 있었다: (1) co-occurrence boost 가 후보마다
문장 단어를 재순회, (2) _DETERMINISTIC_HINTS 이메일 패턴이 긴 영숫자열에서 백트래킹.
둘 다 닫혔고, 이 테스트가 재발을 잡는다(보수적 상한이라 느린 CI 에서도 안전).
"""
from __future__ import annotations

import time
import gc
from statistics import median

import pytest

from ko_pii import Anonymizer, detect_all
from ko_pii.patterns import email
from ko_pii.patterns import account
from ko_pii.patterns import address, birth, person
from ko_pii.context.name_fields import next_field_after_name


def _elapsed(text: str) -> float:
    # Start each sample at the same GC phase; keep GC enabled during the call.
    # Otherwise garbage from earlier tests can be charged only to the large input.
    gc.collect()
    # Measure algorithmic CPU cost rather than scheduler wait. Wall-clock
    # thresholds produce false failures in CPU-quota CI/shared environments.
    start = time.process_time()
    detect_all(text)
    return time.process_time() - start


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


@pytest.mark.parametrize("strategy", ["redact", "tokenize"])
def test_dense_phone_processing_stays_sub_quadratic(strategy: str) -> None:
    def elapsed(count: int) -> float:
        text = "010-1234-5678\n" * count
        samples = []
        for _ in range(3):
            anon = Anonymizer(strategy=strategy, include=["PHONE"])
            gc.collect()
            start = time.process_time()
            result = anon.process(text)
            samples.append(time.process_time() - start)
            assert len(result.detections) == count
        return median(samples)

    small, large = elapsed(1_000), elapsed(4_000)
    assert large < small * 8, f"dense {strategy} scaling: {small:.3f}s -> {large:.3f}s"


@pytest.mark.parametrize("suffix", ["", "@", " [at] invalid-domain", " [at] example [dot] com"])
def test_email_long_local_run_without_valid_domain_does_not_retry_each_word(suffix: str) -> None:
    text = "word " * 10_000 + suffix
    start = time.process_time()
    found = list(email.detect(text))
    assert time.process_time() - start < 1.0
    assert len(found) == int(suffix.endswith("com"))


@pytest.mark.parametrize("anchor", ["계좌", "계좌번호", "신한은행", '계좌번호= "'])
def test_account_label_without_a_value_does_not_partition_long_whitespace(anchor: str) -> None:
    text = anchor + " " * 100_000 + "X"
    start = time.process_time()
    assert list(account.detect(text)) == []
    assert time.process_time() - start < 1.0


def test_dense_account_bank_anchors_stay_sub_quadratic() -> None:
    def elapsed(count: int) -> float:
        source = "신한은행 110-123-456789\n" * count
        samples = []
        for _ in range(3):
            gc.collect()
            start = time.process_time()
            result = list(account.detect(source))
            samples.append(time.process_time() - start)
            assert len(result) == count
        return median(samples)

    small, large = elapsed(1_000), elapsed(4_000)
    assert large < small * 8, f"account scaling: {small:.3f}s -> {large:.3f}s"


@pytest.mark.parametrize("detector,row,count_per_row", [
    (address.detect, "주소: 서울특별시 강남구 테헤란로 152\n", 1),
    (birth.detect, "생년월일: 1988-01-01\n", 1),
    (person.detect, "홍길동 010-1234-5678\n", 1),
    (person.detect, "성명: 김다은, 박보라\n", 2),
    (person.detect, "성명: N/A, 김다은, None, 박보라\n", 2),
])
def test_dense_korean_records_stay_sub_quadratic(detector, row, count_per_row) -> None:
    def elapsed(count: int) -> float:
        source = row * count
        samples = []
        for _ in range(3):
            gc.collect()
            start = time.process_time()
            found = list(detector(source))
            samples.append(time.process_time() - start)
            assert len(found) == count * count_per_row
        return median(samples)

    small, large = elapsed(500), elapsed(2_000)
    assert large < small * 8, f"dense record scaling: {small:.3f}s -> {large:.3f}s"


@pytest.mark.parametrize("prefix", ["Alias", "A" * 119])
@pytest.mark.parametrize("excluded", [False, True])
def test_many_distinct_literal_names_and_repeated_mentions_stay_sub_quadratic(prefix: str, excluded: bool) -> None:
    def name(index: int) -> str:
        suffix = ""
        for _ in range(4):
            index, digit = divmod(index, 26)
            suffix = chr(65 + digit) + suffix
        return prefix + " " + suffix

    def elapsed(count: int) -> float:
        source = "\n".join("성명: " + name(index) + "\n" + name(index) for index in range(count))
        exclusions = [name(index) for index in range(count)] if excluded else None
        samples = []
        for _ in range(3):
            gc.collect()
            start = time.process_time()
            found = list(person.detect(source, exclusions=exclusions))
            samples.append(time.process_time() - start)
            assert len(found) == (0 if excluded else count * 2)
        return median(samples)

    small, large = elapsed(500), elapsed(2_000)
    assert large < small * 8, f"literal name scaling: {small:.3f}s -> {large:.3f}s"


@pytest.mark.parametrize("tail", ["X", "(", "(work)", "(work)X"])
@pytest.mark.parametrize("key", ["전화번호", "신청인", "고객 전화번호", "customer_email"])
def test_following_field_without_a_colon_does_not_partition_long_whitespace(tail, key):
    source = " " + key + " " * 100_000 + tail
    start = time.process_time()
    assert not next_field_after_name(source, 0)
    assert time.process_time() - start < 1.0


def test_dense_forms_with_following_metadata_stay_sub_quadratic():
    def elapsed(count: int) -> float:
        source = "성명: John Smith **전화번호**: public 생년월일(양력): public\n" * count
        samples = []
        for _ in range(3):
            gc.collect()
            start = time.process_time()
            found = list(person.detect(source))
            samples.append(time.process_time() - start)
            assert len(found) == count
        return median(samples)
    small, large = elapsed(500), elapsed(2_000)
    assert large < small * 8, f"form metadata scaling: {small:.3f}s -> {large:.3f}s"
