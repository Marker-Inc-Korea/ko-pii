from ko_pii.core.types import RiskLevel
from ko_pii.patterns.person import detect


def _detect(text):
    return list(detect(text))


class TestPersonPositive:
    def test_field_label_anchor(self):
        results = _detect("성명: 홍길동")
        assert any(r.text == "홍길동" for r in results)
        r = next(r for r in results if r.text == "홍길동")
        assert r.label == "PERSON"
        assert r.risk_level == RiskLevel.HIGH

    def test_title_anchor(self):
        results = _detect("기획재정부 김철수 과장이 보고했다.")
        names = {r.text for r in results}
        assert "김철수" in names

    def test_title_before_name(self):
        results = _detect("회의에 과장 박영수가 참석했다.")
        names = {r.text for r in results}
        assert "박영수" in names

    def test_compound_surname(self):
        results = _detect("성명: 남궁민수")
        names = {r.text for r in results}
        assert "남궁민수" in names

    def test_particle_handled(self):
        # 홍길동이 → stem "홍길동"
        results = _detect("성명: 홍길동이 신청서를 제출했다.")
        names = {r.text for r in results}
        assert "홍길동" in names

    def test_rrn_proximity_helps_weak_candidate(self):
        # No field label, no title, but RRN right next to it
        results = _detect("이순신 880101-1234568")
        names = {r.text for r in results}
        assert "이순신" in names

    def test_cumulative_dictionary(self):
        # First occurrence strong (field label), second weak (just floating)
        text = "성명: 김민지\n... 본 안건과 관련하여 김민지의 의견을 수렴함."
        results = _detect(text)
        positions = [(r.text, r.start) for r in results if r.text == "김민지"]
        assert len(positions) >= 2

    def test_multiple_names_in_text(self):
        text = "신청인: 홍길동, 보호자: 김영희"
        results = _detect(text)
        names = {r.text for r in results}
        assert {"홍길동", "김영희"}.issubset(names)


class TestPersonNegative:
    def test_common_word_dropped(self):
        results = _detect("김치는 한국의 대표 음식이다.")
        assert not any(r.text == "김치" for r in results)

    def test_no_surname_no_anchor_dropped(self):
        # "길동" has no leading surname and no field label → skip
        assert not any(r.text == "길동" for r in _detect("길동이라는 단어"))

    def test_agency_alone_not_a_person(self):
        results = _detect("기획재정부는 입장을 밝혔다.")
        names = {r.text for r in results}
        assert "기획재정부" not in names

    def test_single_char_no_boost_dropped(self):
        # Just a stray single-char surname-letter → not a name
        results = _detect("이 사건에 대하여")
        assert not any(r.text == "이" for r in results)


class TestPersonStructure:
    def test_span_indices(self):
        text = "성명: 홍길동"
        results = _detect(text)
        r = next(r for r in results if r.text == "홍길동")
        assert text[r.start:r.end] == "홍길동"

    def test_legal_basis_attached(self):
        results = _detect("성명: 홍길동")
        r = next(r for r in results if r.text == "홍길동")
        assert r.legal_basis == "개인정보보호법 제2조"
        assert r.extra["category"] == "일반개인정보"

    def test_evidence_includes_signal_tags(self):
        results = _detect("성명: 홍길동")
        r = next(r for r in results if r.text == "홍길동")
        assert any("field_label" in e for e in r.evidence)
