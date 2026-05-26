from ko_pii.core.types import RiskLevel
from ko_pii.patterns.fax import detect


def _d(text):
    return list(detect(text))


class TestFaxPositive:
    def test_with_keyword_kor(self):
        results = _d("팩스 02-123-4567")
        assert len(results) == 1
        r = results[0]
        assert r.label == "FAX"
        assert r.text == "02-123-4567"
        assert r.risk_level == RiskLevel.LOW

    def test_with_keyword_eng(self):
        assert len(_d("FAX: 02-123-4567")) == 1
        assert len(_d("fax 02 123 4567")) == 1

class TestFaxNegative:
    def test_no_keyword_no_match(self):
        # Without a fax-keyword anchor it must not be claimed by this module
        assert _d("02-123-4567") == []

    def test_removed_jeonsong_keyword(self):
        # "전송" 키워드는 FP 위험으로 제거됨 — 일반 동사 충돌
        assert _d("전송 031-123-4567") == []

    def test_removed_f_dot_keyword(self):
        # "F." 키워드는 FP 위험으로 제거됨 (Grade F. 등 약자 충돌)
        assert _d("F. 02-123-4567") == []

    def test_unrelated_keyword(self):
        assert _d("주소: 02-123-4567") == []


class TestFaxStructure:
    def test_legal_basis(self):
        r = _d("팩스 02-123-4567")[0]
        assert r.legal_basis == "개인정보보호법 제2조"
        assert r.extra["category"] == "일반개인정보"

    def test_evidence_includes_keyword(self):
        r = _d("FAX: 02-123-4567")[0]
        assert any(e.startswith("keyword:") for e in r.evidence)
