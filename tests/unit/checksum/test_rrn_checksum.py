import pytest

from ko_pii.checksum.rrn_checksum import compute_check_digit, is_valid_checksum

VALID_RRNS = [
    "8801011234568",   # 1988-01-01, M (gender=1)
    "9501012345676",   # 1995-01-01, F (gender=2)
    "9901011234563",   # 1999-01-01, M
    "8503152345678",   # 1985-03-15, F
    "8503155345676",   # 1985-03-15, foreigner M (gender=5)
]


@pytest.mark.parametrize("rrn", VALID_RRNS)
def test_valid_rrns_pass_checksum(rrn):
    assert is_valid_checksum(rrn) is True


def test_compute_check_digit_known_values():
    assert compute_check_digit("880101123456") == 8
    assert compute_check_digit("950101234567") == 6
    assert compute_check_digit("850315234567") == 8


def test_invalid_checksum_detected():
    # last digit deliberately wrong
    assert is_valid_checksum("8801011234567") is False
    assert is_valid_checksum("9501012345670") is False


def test_non_numeric_rejected():
    assert is_valid_checksum("880101-1234568") is False  # hyphen present
    assert is_valid_checksum("8801011234a68") is False
    assert is_valid_checksum("") is False
    assert is_valid_checksum("abc") is False


def test_wrong_length_rejected():
    assert is_valid_checksum("123") is False
    assert is_valid_checksum("12345678901234") is False  # 14 digits
    assert is_valid_checksum("123456789012") is False    # 12 digits


def test_compute_check_digit_rejects_bad_input():
    with pytest.raises(ValueError):
        compute_check_digit("12345")
    with pytest.raises(ValueError):
        compute_check_digit("12345678901a")
    with pytest.raises(ValueError):
        compute_check_digit("1234567890123")  # 13 digits, not 12
