import pytest

from ko_pii.checksum.business_reg_checksum import (
    compute_check_digit,
    is_valid_checksum,
)

VALID_BUSINESS_NUMBERS = [
    "1048149532",   # 104-81-49532 (often cited as a 국세청 example)
    "1234567891",   # 123-45-67891 (computed)
    "9876543215",   # 987-65-43215 (computed)
    "2208162517",   # 220-81-62517 (computed)
]


@pytest.mark.parametrize("num", VALID_BUSINESS_NUMBERS)
def test_valid_business_numbers_pass_checksum(num):
    assert is_valid_checksum(num) is True


def test_compute_check_digit_known_values():
    assert compute_check_digit("104814953") == 2
    assert compute_check_digit("123456789") == 1
    assert compute_check_digit("987654321") == 5
    assert compute_check_digit("220816251") == 7


def test_invalid_checksum_detected():
    assert is_valid_checksum("1234567890") is False  # check digit should be 1
    assert is_valid_checksum("1048149530") is False  # should be 2


def test_non_numeric_rejected():
    assert is_valid_checksum("104-81-49532") is False
    assert is_valid_checksum("104814953a") is False
    assert is_valid_checksum("") is False


def test_wrong_length_rejected():
    assert is_valid_checksum("12345") is False
    assert is_valid_checksum("12345678901") is False  # 11 digits
    assert is_valid_checksum("123456789") is False    # 9 digits


def test_compute_check_digit_rejects_bad_input():
    with pytest.raises(ValueError):
        compute_check_digit("123")
    with pytest.raises(ValueError):
        compute_check_digit("12345678a")
    with pytest.raises(ValueError):
        compute_check_digit("1234567890")  # 10 digits, not 9
