from ko_pii.core.types import RiskLevel
from ko_pii.patterns.corp_reg import detect


def _detect_list(text):
    return list(detect(text))


class TestCorpRegPositive:
    def test_kepco_corp_number(self):
        # 191211-0006637 — date-like prefix (19-12-11) but RRN checksum fails
        # so disambiguation correctly emits as CORP_REG.
        results = _detect_list("법인등록번호 191211-0006637")
        assert len(results) == 1
        r = results[0]
        assert r.label == "CORP_REG"
        assert r.text == "191211-0006637"
        assert r.risk_level == RiskLevel.MEDIUM
        assert r.confidence == 1.0

    def test_invalid_date_prefix(self):
        # 99-00-99 — month 0 invalid; clearly not a date.
        results = _detect_list("법인 990099-0000004")
        assert len(results) == 1
        assert results[0].label == "CORP_REG"

    def test_without_hyphen(self):
        results = _detect_list("1912110006637")
        assert len(results) == 1
        assert results[0].label == "CORP_REG"

    def test_legal_basis_attached(self):
        results = _detect_list("191211-0006637")
        assert "상법" in results[0].legal_basis or "법인" in results[0].legal_basis
        assert results[0].extra["category"] == "법인식별정보"


class TestCorpRegDisambiguation:
    def test_valid_rrn_not_claimed(self):
        # 880101-1234568 is a real RRN (all checks pass) — corp_reg must skip.
        assert _detect_list("880101-1234568") == []

    def test_valid_frn_not_claimed(self):
        # 850315-5345676 is a valid FRN — corp_reg must skip.
        assert _detect_list("850315-5345676") == []


class TestCorpRegNegative:
    def test_invalid_corp_checksum(self):
        assert _detect_list("191211-0006630") == []

    def test_too_short(self):
        assert _detect_list("191211-000663") == []

    def test_embedded_in_longer_digit_run(self):
        assert _detect_list("12345678901234") == []
