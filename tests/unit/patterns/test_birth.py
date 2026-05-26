"""DT_BIRTH 생년월일 검출 테스트."""
from ko_pii.patterns.birth import detect


def _d(text):
    return list(detect(text))


class TestBirthKorean:
    def test_full_korean_with_keyword(self):
        r = _d("생년월일: 1988년 1월 1일")
        assert len(r) == 1
        assert r[0].text == "1988년 1월 1일"
        assert r[0].extra["year"] == 1988

    def test_short_year_with_marker(self):
        r = _d("88년생 입니다")
        assert len(r) == 1
        assert r[0].text == "88년생"
        assert r[0].extra["year"] == 1988

    def test_zero_padded(self):
        r = _d("생일은 1995년 03월 15일")
        assert len(r) == 1
        assert r[0].extra["year"] == 1995
        assert r[0].extra["month"] == 3

    def test_keyword_생일(self):
        assert len(_d("생일 1990년 5월 5일")) == 1

    def test_keyword_출생(self):
        assert len(_d("출생 1985년 12월 31일")) == 1

    def test_dob_english_keyword(self):
        assert len(_d("DOB: 1988년 1월 1일")) == 1


class TestBirthNumeric:
    def test_dot_separator(self):
        r = _d("생일은 1988.01.01")
        assert len(r) == 1
        assert r[0].extra["format"] == "numeric"

    def test_hyphen_separator(self):
        r = _d("생년월일 1988-01-01")
        assert len(r) == 1
        assert r[0].extra["year"] == 1988

    def test_slash_separator(self):
        r = _d("생일 1988/01/01")
        assert len(r) == 1

    def test_two_digit_year(self):
        r = _d("생일 88.01.01")
        assert len(r) == 1
        assert r[0].extra["year"] == 1988


class TestBirthNegative:
    def test_meeting_date_rejected(self):
        # 키워드 없는 단순 날짜 (회의·발행일 등)
        assert _d("회의는 2024년 4월 15일") == []

    def test_invalid_month_rejected(self):
        assert _d("생년월일 1988년 13월 1일") == []

    def test_invalid_day_rejected(self):
        assert _d("생일 1988년 2월 30일") == []

    def test_future_year_rejected(self):
        assert _d("생일 2050년 1월 1일") == []

    def test_pre_1900_rejected(self):
        assert _d("생일 1850년 1월 1일") == []

    def test_leap_year(self):
        # 1988 is leap year → Feb 29 valid
        assert len(_d("생년월일 1988년 2월 29일")) == 1
        # 1987 is not leap → Feb 29 invalid
        assert _d("생년월일 1987년 2월 29일") == []

    def test_numeric_without_keyword_rejected(self):
        # 숫자 형식은 키워드 anchor 필수
        assert _d("그날은 1988.01.01 이었다") == []
