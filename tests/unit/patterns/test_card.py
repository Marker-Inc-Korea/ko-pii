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
