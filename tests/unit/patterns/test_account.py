from ko_pii.core.types import RiskLevel
from ko_pii.patterns.account import detect


def _detect_list(text):
    return list(detect(text))


class TestAccountPositive:
    def test_with_keyword(self):
        results = _detect_list("계좌: 110-123-456789")
        assert len(results) == 1
        r = results[0]
        assert r.label == "ACCOUNT"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["digits"] == "110123456789"

    def test_keyword_with_번호(self):
        results = _detect_list("계좌번호 1234567890123")
        assert len(results) == 1
        assert results[0].extra["digits"] == "1234567890123"

    def test_hyphenated_short(self):
        results = _detect_list("계좌 123-45-6789012")
        assert len(results) == 1


class TestAccountNegative:
    def test_no_keyword(self):
        # No 계좌 → not detected
        assert _detect_list("110-123-456789") == []

    def test_too_short(self):
        # 8 digits < 10 minimum
        assert _detect_list("계좌 12345678") == []

    def test_too_long(self):
        # 17 digits > 16 maximum
        assert _detect_list("계좌 12345678901234567") == []
