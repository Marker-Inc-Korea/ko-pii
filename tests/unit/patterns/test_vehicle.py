from ko_pii.core.types import RiskLevel
from ko_pii.patterns.vehicle import detect


def _detect_list(text):
    return list(detect(text))


class TestVehiclePositive:
    def test_standard_2digit_prefix(self):
        results = _detect_list("차량번호 12가3456")
        assert len(results) == 1
        r = results[0]
        assert r.label == "VEHICLE"
        assert r.text == "12가3456"
        assert r.risk_level == RiskLevel.LOW
        assert r.extra["prefix"] == "12"
        assert r.extra["purpose_char"] == "가"
        assert r.extra["suffix"] == "3456"

    def test_3digit_prefix(self):
        results = _detect_list("123가4567")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "123"

    def test_with_spaces(self):
        results = _detect_list("12가 3456")
        assert len(results) == 1

    def test_commercial_purpose_char(self):
        results = _detect_list("운수회사 차량 45바6789")
        assert len(results) == 1
        assert results[0].extra["purpose_char"] == "바"


class TestVehicleNegative:
    def test_digits_only(self):
        assert _detect_list("12345678") == []

    def test_korean_only(self):
        assert _detect_list("가나다") == []

    def test_3digit_suffix(self):
        assert _detect_list("12가345") == []

    def test_5digit_suffix(self):
        # Lookahead blocks (next would be digit)
        assert _detect_list("12가34567") == []

    def test_prefix_too_long(self):
        # 4-digit "prefix" is not a valid plate format
        assert _detect_list("1234가5678") == []
