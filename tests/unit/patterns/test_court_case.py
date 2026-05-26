from ko_pii.core.types import RiskLevel
from ko_pii.patterns.court_case import detect


def _d(text):
    return list(detect(text))


class TestCourtCasePositive:
    def test_civil_first_instance(self):
        r = _d("사건번호: 2020가단578")[0]
        assert r.label == "COURT_CASE"
        assert r.text == "2020가단578"
        assert r.extra["year"] == "2020"
        assert r.extra["case_code"] == "가단"
        assert r.extra["serial"] == "578"
        assert r.extra["instance"] == "civil_1st_single"

    def test_civil_panel(self):
        assert _d("2024가합12345")[0].extra["instance"] == "civil_1st_panel"

    def test_criminal(self):
        r = _d("2023고합567")[0]
        assert r.extra["instance"] == "criminal_1st_panel"
        assert r.risk_level == RiskLevel.MEDIUM

    def test_administrative(self):
        assert _d("2024구합1234")[0].extra["instance"] == "admin_1st_panel"

    def test_constitutional(self):
        assert _d("2024헌마567")[0].extra["case_code"] == "헌마"

    def test_appellate(self):
        assert _d("2024나1234")[0].extra["instance"] == "civil_2nd"
        assert _d("2024노5678")[0].extra["instance"] == "criminal_2nd"


class TestCourtCaseNegative:
    def test_year_alone(self):
        assert _d("2024년 사건") == []

    def test_unknown_code(self):
        assert _d("2024XX1234") == []

    def test_serial_zero(self):
        # 일련번호 0 만 → placeholder 거부
        assert _d("2024가합0") == []

    def test_no_year(self):
        assert _d("가합1234") == []


class TestCourtCaseStructure:
    def test_legal_basis(self):
        r = _d("2024가합12345")[0]
        assert "민사소송법" in r.legal_basis
