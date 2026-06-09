from ko_pii.core.types import RiskLevel
from ko_pii.patterns.medical_insurance import detect


def _detect_list(text):
    return list(detect(text))


class TestMedicalInsurancePositive:
    def test_with_health_insurance_keyword(self):
        results = _detect_list("건강보험증 번호: 12345678901")
        assert len(results) == 1
        r = results[0]
        assert r.label == "MEDICAL_INSURANCE"
        assert r.text == "12345678901"
        assert r.risk_level == RiskLevel.HIGH
        assert r.extra["digits"] == "12345678901"

    def test_with_medical_insurance_keyword(self):
        results = _detect_list("의료보험 11111222223")
        assert len(results) == 1

    def test_with_insurance_card_keyword(self):
        results = _detect_list("보험증 99988877766")
        assert len(results) == 1

    def test_keyword_with_spacing(self):
        results = _detect_list("건강 보험 가입자: 55544433322")
        assert len(results) == 1


class TestMedicalInsuranceNegative:
    def test_no_keyword_context(self):
        # 11-digit run without any insurance keyword
        assert _detect_list("주문번호 12345678901 처리됨") == []

    def test_keyword_too_far_away(self):
        # 건강보험 mentioned > 40 chars before the number
        far_text = "건강보험 관련 안내문에 따른 처리는 매우 복잡한 절차를 거치게 됩니다 12345678901"
        assert _detect_list(far_text) == []

    def test_phone_number_not_misdetected(self):
        # 11-digit phone without insurance context
        assert _detect_list("연락처: 01012345678") == []

    def test_too_short(self):
        assert _detect_list("건강보험 1234567890") == []  # 10 digits

    def test_too_long(self):
        assert _detect_list("건강보험 123456789012") == []  # 12 digits


class TestMedicalInsuranceStructure:
    def test_span_indices_correct(self):
        text = "건강보험 12345678901 입력 완료"
        results = _detect_list(text)
        assert len(results) == 1
        r = results[0]
        assert text[r.start:r.end] == "12345678901"


class TestMedicalInsuranceDashed:
    """증번호 표기형 N-NNNNNNNNNN (종별코드 + 하이픈 + 10자리)."""

    def test_dashed_card_number(self):
        results = _detect_list("건강보험증번호: 1-2840193756")
        assert len(results) == 1
        assert results[0].text == "1-2840193756"

    def test_dashed_other_code(self):
        assert _detect_list("의료보험 5-1098372214")[0].text == "5-1098372214"

    def test_dashed_requires_keyword(self):
        assert _detect_list("계좌번호 1-2840193756") == []
