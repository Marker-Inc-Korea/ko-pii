from ko_pii.core.types import RiskLevel
from ko_pii.patterns.prescription import detect


def _d(text):
    return list(detect(text))


class TestPrescriptionIssuancePositive:
    def test_basic_with_keyword(self):
        results = _d("처방번호: 202412010001")
        assert len(results) == 1
        r = results[0]
        assert r.label == "PRESCRIPTION_ID"
        assert r.text == "202412010001"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["subtype"] == "issuance_id"
        assert r.extra["issue_date"] == "2024-12-01"
        assert r.extra["serial"] == "0001"

    def test_korean_keyword_variants(self):
        for kw in ("처방번호", "처방전번호", "처방전 발행번호", "교부번호"):
            assert len(_d(f"{kw}: 202401150042")) == 1

    def test_rx_keyword(self):
        assert len(_d("Rx 202401150042")) == 1
        assert len(_d("Rx 번호: 202401150042")) == 1


class TestPrescriptionIssuanceNegative:
    def test_no_keyword(self):
        # 12자리 숫자 자체로는 검출 안 됨
        assert _d("202412010001") == []

    def test_invalid_date(self):
        # 13월
        assert _d("처방번호: 202413010001") == []
        # 0월
        assert _d("처방번호: 202400010001") == []
        # 2월 30일
        assert _d("처방번호: 202402300001") == []

    def test_year_out_of_range(self):
        assert _d("처방번호: 198912010001") == []

    def test_wrong_digit_count(self):
        # 11자리
        assert _d("처방번호: 20241201000") == []
        # 13자리
        assert _d("처방번호: 2024120100012") == []

    def test_keyword_too_far(self):
        # 키워드가 너무 멀리 떨어져 있으면 매칭 안 됨
        text = "처방번호 입력란 안내 이후 한참 떨어진 곳에 적혀 있는 202412010001"
        assert _d(text) == []


class TestInstitutionCode:
    def test_with_keyword(self):
        results = _d("의료기관기호: 12345678")
        assert len(results) == 1
        r = results[0]
        assert r.extra["subtype"] == "institution_id"
        assert r.extra["value"] == "12345678"
        assert r.risk_level == RiskLevel.MEDIUM

    def test_alternate_keywords(self):
        assert len(_d("요양기관기호 12345678")) == 1
        assert len(_d("병원코드: 98765432")) == 1

    def test_no_keyword_no_match(self):
        assert _d("12345678") == []


class TestPrescriptionStructure:
    def test_legal_basis(self):
        r = _d("처방번호 202412010001")[0]
        assert "의료법" in r.legal_basis
        assert "약사법" in r.legal_basis
        assert r.extra["category"] == "민감정보(건강)"

    def test_evidence_includes_date(self):
        r = _d("처방번호 202412010001")[0]
        assert any(e.startswith("date_valid:") for e in r.evidence)


class TestPrescriptionLabeledId:
    """EMR 영문 접두 처방번호 (RX-/PRSC- 등) — 키워드 anchor 필수."""

    def test_rx_prefix(self):
        r = _d("처방번호 RX-2026-008471")
        assert len(r) == 1
        assert r[0].text == "RX-2026-008471"

    def test_prsc_multi_segment(self):
        assert _d("처방번호: PRSC-2026-0053-77192")[0].text == "PRSC-2026-0053-77192"

    def test_kyobu_keyword(self):
        assert _d("교부번호 RX-260503-44120")[0].text == "RX-260503-44120"

    def test_labeled_requires_keyword(self):
        assert _d("주문 RX-2026-008471") == []
