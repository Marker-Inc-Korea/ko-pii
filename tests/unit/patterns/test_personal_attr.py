"""EDUCATION / MAJOR / POSITION / AGE / HEIGHT / WEIGHT 검출 테스트."""
from ko_pii.patterns.personal_attr import detect


def _d(text, label=None):
    results = list(detect(text))
    if label:
        return [r for r in results if r.label == label]
    return results


class TestEducation:
    def test_seoul_national(self):
        r = _d("서울대학교 졸업", "EDUCATION")
        assert len(r) == 1
        assert r[0].text == "서울대학교"

    def test_yonsei(self):
        assert len(_d("연세대학교 신촌캠퍼스", "EDUCATION")) == 1

    def test_kaist(self):
        r = _d("KAIST 출신", "EDUCATION")
        assert len(r) == 1

    def test_kaist_korean(self):
        assert len(_d("카이스트 출신", "EDUCATION")) == 1

    def test_postech(self):
        assert len(_d("POSTECH 졸업", "EDUCATION")) == 1

    def test_unknown_university_rejected(self):
        # 사전에 없는 가상 학교명 거부
        assert _d("가짜대학교 다님", "EDUCATION") == []


class TestMajor:
    def test_engineering(self):
        r = _d("컴퓨터공학과 학생", "MAJOR")
        assert len(r) == 1
        assert r[0].text == "컴퓨터공학과"

    def test_business(self):
        assert len(_d("경영학부 출신", "MAJOR")) == 1

    def test_law(self):
        assert len(_d("법학 전공", "MAJOR")) == 1

    def test_medical(self):
        assert len(_d("의예과 학생", "MAJOR")) == 1

    def test_normalize_suffix(self):
        # "컴퓨터공학과" → canonical "컴퓨터공학"
        r = _d("컴퓨터공학과 졸업", "MAJOR")[0]
        assert r.extra["canonical"] == "컴퓨터공학"

    def test_unknown_rejected(self):
        # 사전에 없는 가짜 전공 거부
        assert _d("뽀로로공학과", "MAJOR") == []


class TestPosition:
    def test_jiggeup_keyword(self):
        r = _d("직급: 사무관", "POSITION")
        assert len(r) == 1
        assert r[0].text == "사무관"

    def test_jikchaek_keyword(self):
        assert len(_d("직책 부장", "POSITION")) == 1

    def test_no_keyword_rejected(self):
        # 키워드 없으면 단독 emit X (PERSON 컨텍스트로만 사용)
        assert _d("사무관이 결재", "POSITION") == []


class TestMeasurements:
    def test_age_se(self):
        r = _d("나이 32세", "AGE")
        assert len(r) == 1
        assert r[0].extra["value"] == 32

    def test_age_sal(self):
        assert len(_d("32살", "AGE")) == 1

    def test_height_cm(self):
        r = _d("키 175cm", "HEIGHT")
        assert len(r) == 1
        assert r[0].extra["value"] == 175

    def test_height_korean(self):
        assert len(_d("175센티", "HEIGHT")) == 1

    def test_weight_kg(self):
        r = _d("70kg", "WEIGHT")
        assert len(r) == 1
        assert r[0].extra["value"] == 70

    def test_weight_korean(self):
        assert len(_d("70킬로", "WEIGHT")) == 1

    def test_age_out_of_range(self):
        # 200세 = 비현실
        assert _d("200세", "AGE") == []

    def test_weight_too_heavy(self):
        # 500kg = 사람 아님
        assert _d("500kg", "WEIGHT") == []
