from ko_pii.core.types import RiskLevel
from ko_pii.patterns.postal_code import detect


def _detect_list(text):
    return list(detect(text))


class TestPostalCodePositive:
    def test_new_5digit_with_keyword(self):
        results = _detect_list("우편번호 06234")
        assert len(results) == 1
        r = results[0]
        assert r.label == "POSTAL_CODE"
        assert r.text == "06234"
        assert r.extra["format"] == "5_digit"
        assert r.risk_level == RiskLevel.LOW

    def test_new_5digit_with_colon(self):
        results = _detect_list("우편번호: 03001")
        assert len(results) == 1
        assert results[0].text == "03001"

    def test_new_5digit_keyword_short(self):
        results = _detect_list("우편 13561")
        assert len(results) == 1

    def test_legacy_6digit(self):
        results = _detect_list("주소: 서울시 강남구 (135-080)")
        assert len(results) == 1
        assert results[0].extra["format"] == "6_digit"
        assert results[0].text == "135-080"


class TestPostalCodeNegative:
    def test_5digit_without_keyword(self):
        # Just a number, no 우편 keyword
        assert _detect_list("결재번호 12345") == []

    def test_too_short_5digit(self):
        assert _detect_list("우편번호 1234") == []

    def test_too_long_5digit(self):
        assert _detect_list("우편번호 123456") == []

    def test_invalid_6digit_format(self):
        # 4-3 pattern, not 3-3
        assert _detect_list("1234-567") == []
