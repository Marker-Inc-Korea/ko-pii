import pytest

from ko_pii.checksum.corp_reg_checksum import compute_check_digit, is_valid_checksum

# 공식 법인등록번호 규격(가중치 1,2 교대 + 곱을 그대로 합산, check=(10-합%10)%10)으로
# 검증한 값. 구현이 아니라 사양 기준 — 삼성전자는 DART 공시로 외부 검증 가능한 실번호.
VALID_CORP_NUMBERS = [
    "1301110006246",   # 삼성전자 (DART 검증, 실제 13번째 자리 6)
    "1912110006639",   # 한전 prefix 191211-000663 + 올바른 check digit 9
    "1311110000007",   # synthetic: registry code + zero sequence (check 7)
]


@pytest.mark.parametrize("num", VALID_CORP_NUMBERS)
def test_valid_corp_numbers_pass_checksum(num):
    assert is_valid_checksum(num) is True


def test_compute_check_digit_known_values():
    assert compute_check_digit("130111000624") == 6   # 삼성전자 (실번호)
    assert compute_check_digit("191211000663") == 9   # 한전
    assert compute_check_digit("990099000000") == 6


def test_luhn_style_value_is_rejected():
    # 과거 Luhn식(자릿수 축약) 구현이 삼성 번호의 check digit 을 5 로 잘못 계산했음.
    # 올바른 알고리즘에선 6 이므로 ...6245 는 무효, ...6246 만 유효.
    assert is_valid_checksum("1301110006245") is False
    assert is_valid_checksum("1301110006246") is True


def test_invalid_checksum_detected():
    assert is_valid_checksum("1912110006637") is False  # 올바른 check 는 9


def test_non_numeric_rejected():
    assert is_valid_checksum("191211-0006639") is False  # hyphen present
    assert is_valid_checksum("191211000663a") is False
    assert is_valid_checksum("") is False


def test_wrong_length_rejected():
    assert is_valid_checksum("123") is False
    assert is_valid_checksum("12345678901234") is False  # 14 digits
    assert is_valid_checksum("123456789012") is False    # 12 digits


def test_compute_check_digit_rejects_bad_input():
    with pytest.raises(ValueError):
        compute_check_digit("123")
    with pytest.raises(ValueError):
        compute_check_digit("12345678901a")
