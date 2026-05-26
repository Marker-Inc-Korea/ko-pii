from ko_pii.core.types import RiskLevel
from ko_pii.domain.government import detect


def _d(text):
    return list(detect(text))


class TestDocIdPositive:
    def test_basic_doc_id(self):
        results = _d("문서번호: 기재부-인사-2024-00123")
        assert len(results) == 1
        r = results[0]
        assert r.label == "DOC_ID"
        assert r.text == "기재부-인사-2024-00123"
        assert r.risk_level == RiskLevel.LOW

    def test_six_digit_serial(self):
        assert len(_d("행안부-총무과-2025-000567")) == 1

    def test_in_paragraph(self):
        text = "본 안건은 기재부-인사-2024-00123 으로 등록됨."
        results = _d(text)
        assert len(results) == 1


class TestDocIdNegative:
    def test_only_year_serial(self):
        # Not enough structure
        assert _d("2024-00123") == []

    def test_missing_year(self):
        assert _d("기재부-인사-abc-00123") == []

    def test_extra_alphanum_after(self):
        # Boundary check: should not match if trailing alphanumeric
        assert _d("기재부-인사-2024-001234A") == []


class TestDocIdStructure:
    def test_legal_basis(self):
        r = _d("기재부-인사-2024-00123")[0]
        assert r.legal_basis == "개인정보보호법 제2조"
        assert r.extra["domain"] == "government"


class TestDocIdAgencyBoost:
    def test_known_agency_high_confidence(self):
        r = _d("기재부-인사-2024-00123")[0]
        assert r.confidence == 0.95
        assert r.extra["agency_prefix"] == "기재부"
        assert r.extra["agency_normalized"] == "기획재정부"
        assert any("agency_known:" in e for e in r.evidence)

    def test_full_name_prefix_recognized(self):
        r = _d("기획재정부-인사-2024-00123")[0]
        assert r.confidence == 0.95
        assert r.extra["agency_normalized"] == "기획재정부"

    def test_unknown_agency_default_confidence(self):
        r = _d("외계청-부서-2024-00123")[0]
        assert r.confidence == 0.85
        assert r.extra["agency_normalized"] is None

    def test_various_agency_abbrevs(self):
        for abbrev in ("행안부", "복지부", "국토부", "산업부", "방사청"):
            results = _d(f"{abbrev}-총무과-2024-00567")
            assert len(results) == 1
            assert results[0].confidence == 0.95
