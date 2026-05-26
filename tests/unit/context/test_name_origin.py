from ko_pii.context.name_origin import classify_name_origin, is_korean_name, is_foreign_name


class TestKoreanNames:
    def test_typical_korean_names(self):
        for name in ("홍길동", "김민수", "박영수", "이수정", "최지훈",
                     "강도현", "황보경", "남궁민수"):
            assert classify_name_origin(name) == "korean"
            assert is_korean_name(name)
            assert not is_foreign_name(name)

    def test_2char_with_surname(self):
        assert classify_name_origin("이수") == "korean"
        assert classify_name_origin("박미") == "korean"


class TestForeignNames:
    def test_long_names_classified_foreign(self):
        # 5자 이상 한글 인명 = 거의 외래어 (룰로 안전 분리 가능)
        for name in ("소피마르소", "아오이유우", "마이클잭슨"):
            assert classify_name_origin(name) == "foreign"
            assert is_foreign_name(name)

    def test_4char_foreign_limitation(self):
        # 4자 한글 + 한국 surname 시작 = 룰만으론 외래어 판별 어려움
        # ("조지부시" 는 "조" surname 으로 시작 → korean 분류)
        # 이건 룰 기반의 본질적 한계. 사용자가 필요 시 직접 사전 추가.
        assert classify_name_origin("조지부시") == "korean"

    def test_r_initial_foreign(self):
        # ㄹ 두음 시작 = 한국어 두음법칙상 외래어
        for name in ("러셀", "로버트", "리키"):
            assert classify_name_origin(name) == "foreign"


class TestUnknown:
    def test_non_korean_chars(self):
        assert classify_name_origin("Hong Gildong") == "unknown"
        assert classify_name_origin("洪吉童") == "unknown"
        assert classify_name_origin("") == "unknown"

    def test_short_no_surname(self):
        # 2-3자 + surname 아닌 글자 시작 + 외래어 신호 없음 → unknown
        # ("호도" 등 surname 시작 토큰은 korean 으로 분류됨)
        assert classify_name_origin("탇풉") == "unknown"
