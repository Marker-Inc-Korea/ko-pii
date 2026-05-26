import pytest

from ko_pii.checksum.corp_reg_checksum import compute_check_digit, is_valid_checksum

# Verified by hand using the Luhn-like algorithm with weights (1,2) alternating.
VALID_CORP_NUMBERS = [
    "1912110006637",   # 한전 (Korea Electric Power)
    "1311110000007",   # synthetic: registry code + zero sequence
    "9900990000004",   # synthetic: invalid-date prefix
]


@pytest.mark.parametrize("num", VALID_CORP_NUMBERS)
def test_valid_corp_numbers_pass_checksum(num):
    assert is_valid_checksum(num) is True


def test_compute_check_digit_known_values():
    assert compute_check_digit("191211000663") == 7
    assert compute_check_digit("131111000000") == 7
    assert compute_check_digit("990099000000") == 4


def test_invalid_checksum_detected():
    assert is_valid_checksum("1912110006630") is False  # should end in 7


def test_non_numeric_rejected():
    assert is_valid_checksum("191211-0006637") is False  # hyphen present
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
