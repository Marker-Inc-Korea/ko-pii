from ko_pii.core.types import RiskLevel
from ko_pii.domain.hr import detect


def _d(text):
    return list(detect(text))


class TestEmployeeIdPositive:
    def test_sabeon_keyword(self):
        results = _d("사번: 20231234")
        assert len(results) == 1
        assert results[0].label == "EMPLOYEE_ID"
        assert results[0].text == "20231234"

    def test_other_keywords(self):
        assert len(_d("공무원번호 123456")) == 1
        assert len(_d("직원번호: 456789")) == 1
        assert len(_d("임용번호 78901234")) == 1
        assert len(_d("사원번호: 1234567")) == 1


class TestEmployeeIdNegative:
    def test_no_keyword_no_match(self):
        assert _d("20231234") == []

    def test_keyword_too_far(self):
        # 30 chars between keyword and number — outside window
        assert _d("사번 입력 이후 한참 뒤에 적혀있는 번호 12345678") == []

    def test_kyobeon_removed(self):
        # 교번 = 수학·공학의 교차/교번 의미 — FP 위험으로 제거됨
        assert _d("교번 789012") == []

    def test_sabeon_general_sentence_rejected(self):
        # "이것은 사번이 다르다" + 문장 뒤 숫자 → FP 거부
        assert _d("이것은 사번이 다르다 그러므로 20240001") == []

    def test_sabeon_colon_and_space_both_work(self):
        assert len(_d("사번:20240001")) == 1
        assert len(_d("사번: 20240001")) == 1
        assert len(_d("사번 20240001")) == 1
        assert len(_d("사번20240001")) == 1


class TestEmployeeIdStructure:
    def test_legal_basis(self):
        r = _d("사번 20231234")[0]
        assert "국가공무원법" in r.legal_basis
        assert r.risk_level == RiskLevel.MEDIUM
