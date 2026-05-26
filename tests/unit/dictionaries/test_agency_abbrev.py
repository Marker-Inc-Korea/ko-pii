from ko_pii.dictionaries.agency_abbrev import (
    KOR_ABBREV_TO_FULL, ENG_ABBREV_TO_KOR,
    normalize_agency, is_doc_id_prefix,
)


class TestKoreanAbbreviations:
    def test_common_ministry_abbreviations(self):
        assert KOR_ABBREV_TO_FULL["기재부"] == "기획재정부"
        assert KOR_ABBREV_TO_FULL["행안부"] == "행정안전부"
        assert KOR_ABBREV_TO_FULL["과기정통부"] == "과학기술정보통신부"
        assert KOR_ABBREV_TO_FULL["복지부"] == "보건복지부"
        assert KOR_ABBREV_TO_FULL["국토부"] == "국토교통부"

    def test_agency_abbreviations(self):
        assert KOR_ABBREV_TO_FULL["방사청"] == "방위사업청"
        assert KOR_ABBREV_TO_FULL["식약처"] == "식품의약품안전처"
        assert KOR_ABBREV_TO_FULL["우주청"] == "우주항공청"

    def test_commission_abbreviations(self):
        assert KOR_ABBREV_TO_FULL["공정위"] == "공정거래위원회"
        assert KOR_ABBREV_TO_FULL["방통위"] == "방송통신위원회"
        assert KOR_ABBREV_TO_FULL["인권위"] == "국가인권위원회"


class TestEnglishAbbreviations:
    def test_official_english_codes(self):
        # 행안부예규 정부조직 영어명칭 별표
        assert ENG_ABBREV_TO_KOR["MOEF"] == "기획재정부"
        assert ENG_ABBREV_TO_KOR["MOIS"] == "행정안전부"
        assert ENG_ABBREV_TO_KOR["MSIT"] == "과학기술정보통신부"
        assert ENG_ABBREV_TO_KOR["MOFA"] == "외교부"
        assert ENG_ABBREV_TO_KOR["KASA"] == "우주항공청"
        assert ENG_ABBREV_TO_KOR["OKA"] == "재외동포청"
        assert ENG_ABBREV_TO_KOR["KDCA"] == "질병관리청"


class TestNormalize:
    def test_normalize_kor_abbrev(self):
        assert normalize_agency("기재부") == "기획재정부"
        assert normalize_agency("MOEF") == "기획재정부"

    def test_unknown_passthrough(self):
        assert normalize_agency("아무튼") is None


class TestDocIdPrefix:
    def test_known_prefix(self):
        assert is_doc_id_prefix("기재부")
        assert is_doc_id_prefix("기획재정부")
        assert is_doc_id_prefix("행안부")

    def test_unknown_prefix(self):
        assert not is_doc_id_prefix("아무부서")


class TestDictionarySize:
    def test_minimum_coverage(self):
        # We claim 정부조직 약칭 규칙 별표 coverage — at least 30 entries.
        assert len(KOR_ABBREV_TO_FULL) >= 30
        assert len(ENG_ABBREV_TO_KOR) >= 30
