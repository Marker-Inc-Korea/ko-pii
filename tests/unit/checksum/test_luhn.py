import pytest

from ko_pii.checksum.luhn import compute_check_digit, is_valid

# Standard Luhn test vectors used by the payments industry
LUHN_VALID = [
    "4111111111111111",     # Visa test
    "5555555555554444",     # Mastercard test
    "378282246310005",      # Amex test (15)
    "6011111111111117",     # Discover test
    "30569309025904",       # Diners (14)
    "79927398713",          # Wikipedia example
]


@pytest.mark.parametrize("num", LUHN_VALID)
def test_known_valid(num):
    assert is_valid(num) is True


def test_invalid_flip_last_digit():
    assert is_valid("4111111111111112") is False
    assert is_valid("79927398714") is False


def test_non_numeric_rejected():
    assert is_valid("abc") is False
    assert is_valid("4111-1111-1111-1111") is False  # hyphens present


def test_too_short_rejected():
    assert is_valid("4") is False
    assert is_valid("") is False


def test_compute_check_digit_round_trip():
    # For each known card, stripping the last digit and computing should
    # produce the original last digit
    for card in LUHN_VALID:
        payload = card[:-1]
        expected = int(card[-1])
        assert compute_check_digit(payload) == expected
