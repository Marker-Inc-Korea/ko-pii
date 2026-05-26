from ko_pii.core.types import RiskLevel
from ko_pii.patterns.phone import detect


def _detect_list(text):
    return list(detect(text))


class TestPhoneMobile:
    def test_010_hyphen(self):
        results = _detect_list("연락처: 010-1234-5678")
        assert len(results) == 1
        r = results[0]
        assert r.label == "PHONE"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["type"] == "mobile"
        assert r.extra["digits_only"] == "01012345678"

    def test_010_no_separator(self):
        results = _detect_list("01012345678")
        assert len(results) == 1
        assert results[0].extra["type"] == "mobile"

    def test_010_with_spaces(self):
        results = _detect_list("010 1234 5678")
        assert len(results) == 1
        assert results[0].extra["digits_only"] == "01012345678"

    def test_010_with_dots(self):
        results = _detect_list("010.1234.5678")
        assert len(results) == 1

    def test_011_legacy_mobile(self):
        results = _detect_list("011-987-6543")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "011"


class TestPhoneLandline:
    def test_seoul_4_digit_middle(self):
        results = _detect_list("02-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "landline"
        assert results[0].extra["prefix"] == "02"

    def test_seoul_3_digit_middle(self):
        results = _detect_list("02-123-4567")
        assert len(results) == 1
        assert results[0].extra["digits_only"] == "021234567"

    def test_gyeonggi_031(self):
        results = _detect_list("031-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "landline"
        assert results[0].extra["prefix"] == "031"

    def test_busan_051(self):
        results = _detect_list("051-987-6543")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "051"


class TestPhoneVoIP:
    def test_070(self):
        results = _detect_list("070-1234-5678")
        assert len(results) == 1
        assert results[0].extra["type"] == "voip"
        assert results[0].extra["prefix"] == "070"


class TestPhoneNegative:
    def test_unknown_prefix(self):
        # 099 not a valid Korean phone prefix
        assert _detect_list("099-1234-5678") == []

    def test_too_short(self):
        assert _detect_list("010-123-456") == []

    def test_embedded_in_longer_digits(self):
        assert _detect_list("010123456789012") == []

    def test_only_prefix(self):
        assert _detect_list("010") == []
