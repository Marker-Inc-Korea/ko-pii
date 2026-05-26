from ko_pii.core.types import RiskLevel
from ko_pii.patterns.business_reg import detect


def _detect_list(text):
    return list(detect(text))


class TestBusinessRegPositive:
    def test_full_hyphens(self):
        results = _detect_list("사업자등록번호: 104-81-49532")
        assert len(results) == 1
        r = results[0]
        assert r.label == "BUSINESS_REG"
        assert r.text == "104-81-49532"
        assert r.risk_level == RiskLevel.HIGH
        assert r.confidence == 1.0

    def test_no_hyphens(self):
        results = _detect_list("사업자번호 1048149532 입니다")
        assert len(results) == 1
        assert results[0].text == "1048149532"

    def test_partial_hyphens(self):
        results = _detect_list("104-8149532")
        assert len(results) == 1

    def test_multiple_in_one_text(self):
        text = "공급자 104-81-49532, 매입자 123-45-67891"
        results = _detect_list(text)
        assert len(results) == 2
        assert {r.text for r in results} == {"104-81-49532", "123-45-67891"}

    def test_legal_basis_attached(self):
        results = _detect_list("104-81-49532")
        assert results[0].legal_basis is not None
        assert results[0].extra["digits"] == "1048149532"


class TestBusinessRegNegative:
    def test_invalid_checksum(self):
        # check digit deliberately wrong
        assert _detect_list("104-81-49530") == []
        assert _detect_list("1234567890") == []

    def test_too_short(self):
        assert _detect_list("104-81-4953") == []
        assert _detect_list("104814953") == []

    def test_too_long(self):
        # 11 digits no separators — lookarounds block
        assert _detect_list("12345678901") == []

    def test_phone_format_not_matched(self):
        # 010-1234-5678 is 3-4-4 format, not 3-2-5
        assert _detect_list("010-1234-5678") == []

    def test_embedded_in_longer_digits(self):
        # 14-digit run with no separators
        assert _detect_list("12345678901234") == []


class TestBusinessRegStructure:
    def test_span_indices_correct(self):
        text = "사업자 등록증 104-81-49532 발급됨"
        results = _detect_list(text)
        assert len(results) == 1
        r = results[0]
        assert text[r.start:r.end] == "104-81-49532"
