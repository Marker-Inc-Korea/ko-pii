from ko_pii.core.types import RiskLevel
from ko_pii.patterns.passport import detect


def _detect_list(text):
    return list(detect(text))


class TestPassportPositive:
    def test_general_passport_M(self):
        results = _detect_list("여권번호: M12345678")
        assert len(results) == 1
        r = results[0]
        assert r.label == "PASSPORT"
        assert r.text == "M12345678"
        assert r.risk_level == RiskLevel.CRITICAL
        assert r.extra["prefix"] == "M"
        assert r.extra["number"] == "12345678"

    def test_general_passport_S(self):
        results = _detect_list("Passport S87654321")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "S"

    def test_diplomatic_passport_D(self):
        results = _detect_list("외교관 여권 D11223344")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "D"

    def test_official_passport_O(self):
        results = _detect_list("관용 O55667788")
        assert len(results) == 1
        assert results[0].extra["prefix"] == "O"

    def test_legal_basis(self):
        results = _detect_list("M12345678")
        assert "시행령 제19조" in results[0].legal_basis
        assert results[0].extra["category"] == "고유식별정보"

    def test_multiple_passports(self):
        text = "본인 M12345678 / 동반자 S87654321"
        results = _detect_list(text)
        assert len(results) == 2


class TestPassportNegative:
    def test_invalid_prefix_letter(self):
        # X is not a recognized prefix
        assert _detect_list("X12345678") == []

    def test_lowercase_prefix_rejected(self):
        # Korean passports use uppercase
        assert _detect_list("m12345678") == []

    def test_too_few_digits(self):
        assert _detect_list("M1234567") == []

    def test_too_many_digits(self):
        # 9 digits — lookahead blocks (next char is digit)
        assert _detect_list("M123456789") == []

    def test_embedded_in_word(self):
        # Preceded by letter — lookbehind blocks
        assert _detect_list("RoomM12345678") == []
