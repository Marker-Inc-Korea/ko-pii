import pytest

from ko_pii.core.types import RiskLevel
from ko_pii.patterns.card import detect


def _detect_list(text):
    return list(detect(text))


class TestCardPositive:
    def test_visa_16_with_hyphens(self):
        results = _detect_list("카드번호: 4111-1111-1111-1111")
        assert len(results) == 1
        r = results[0]
        assert r.label == "CARD"
        assert r.text == "4111-1111-1111-1111"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["digits"] == "4111111111111111"
        assert r.extra["length"] == 16

    def test_visa_16_with_spaces(self):
        results = _detect_list("4111 1111 1111 1111")
        assert len(results) == 1

    def test_visa_16_no_separator(self):
        results = _detect_list("Card 4111111111111111 valid")
        assert len(results) == 1
        assert results[0].extra["length"] == 16

    def test_mastercard(self):
        results = _detect_list("5555-5555-5555-4444")
        assert len(results) == 1
        assert results[0].extra["digits"] == "5555555555554444"

    def test_amex_15_digits(self):
        # Amex test: 378282246310005 — bare 15-digit run
        results = _detect_list("Amex 378282246310005 issued")
        assert len(results) == 1
        assert results[0].extra["length"] == 15

    def test_multiple_cards_in_text(self):
        text = "본인 4111-1111-1111-1111, 배우자 5555-5555-5555-4444"
        results = _detect_list(text)
        assert len(results) == 2


class TestCardNegative:
    def test_luhn_invalid_rejected(self):
        # Flip last digit so Luhn fails
        assert _detect_list("4111-1111-1111-1112") == []

    def test_too_short(self):
        assert _detect_list("411111111111") == []  # 12 digits

    def test_too_long(self):
        # 20 digits — lookahead blocks
        assert _detect_list("41111111111111111111") == []

    def test_random_digit_run_rejected(self):
        # 16 random digits unlikely to pass Luhn
        assert _detect_list("1234567890123456") == []


@pytest.mark.parametrize("separator", [" ", "-", ".", "/", "- ", "-\n", "-\r\n"])
@pytest.mark.parametrize("groups,digits", [
    (("3782", "822463", "10005"), "378282246310005"),
    (("3056", "930902", "5904"), "30569309025904"),
])
def test_four_six_five_and_four_six_four_formats(separator, groups, digits):
    value = separator.join(groups)
    text = "Card: " + value + " [end]"
    results = _detect_list(text)
    assert len(results) == 1
    assert results[0].text == value
    assert results[0].extra["digits"] == digits
    assert text[results[0].start:results[0].end] == value


@pytest.mark.parametrize("value", [
    "3782 822463 10006",  # Invalid Luhn checksum.
    "1350 000000 00008",  # Unsupported leading digit, valid Luhn checksum.
    "4901 542032 37518",  # IMEI, not a supported 15-digit card prefix.
    "5901 2341 2345 7",  # EAN-13, not a supported 13-digit card prefix.
    "13782 822463 10005",  # Embedded in a longer digit group.
    "3782 822463 100051",  # Too many digits in the final group.
    "2026 111818 12345",  # Date/reference-like groups.
])
def test_formatted_candidates_still_require_existing_validation(value):
    assert _detect_list(value) == []


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t", "\u2028", "\u2029"])
def test_formatted_card_does_not_join_separate_records(separator):
    assert _detect_list(separator.join(("3782", "822463", "10005"))) == []
    assert _detect_list(separator.join(("4111", "1111", "1111", "1111"))) == []


def test_invalid_formatted_card_does_not_hide_following_card():
    results = _detect_list("3782 822463 10006; 3782 822463 10005")
    assert [r.text for r in results] == ["3782 822463 10005"]


@pytest.mark.parametrize("separator", [" ", "-", ".", "/"])
def test_nineteen_digit_card_in_five_groups(separator):
    value = separator.join(("4000", "0000", "0000", "0000", "006"))
    results = _detect_list(value)
    assert len(results) == 1
    assert results[0].text == value
    assert results[0].extra["digits"] == "4000000000000000006"


def test_invalid_nineteen_digit_candidate_is_not_truncated_to_sixteen_digits():
    assert _detect_list("4111 1111 1111 1111 123") == []
