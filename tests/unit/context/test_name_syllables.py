from ko_pii.context.name_syllables import (
    name_likelihood,
    name_shape_bonus,
    syllable_name_score,
)


class TestSyllableScore:
    def test_common_name_syllables(self):
        for s in ("수", "호", "준", "훈", "민", "혁", "현"):
            assert syllable_name_score(s) >= 1.0

    def test_rare_in_names(self):
        for s in ("닭", "삶", "벗"):
            assert syllable_name_score(s) < 0

    def test_unknown_neutral(self):
        # 알려지지 않은 음절 — 약한 중립
        assert syllable_name_score("랄") == 0.2


class TestNameLikelihood:
    def test_typical_korean_name(self):
        # 둘 다 흔한 음절
        assert name_likelihood("홍길동") >= 0.6

    def test_obviously_not_name(self):
        assert name_likelihood("기억") < 0.5
        assert name_likelihood("회의") < 0.5

    def test_short_input(self):
        assert name_likelihood("") == 0.0
        assert name_likelihood("김") == 0.0  # 1자


class TestShapeBonus:
    def test_high_likelihood_max_bonus(self):
        # 매우 흔한 이름 패턴
        assert name_shape_bonus("홍길동") == 0.20

    def test_no_bonus_for_non_names(self):
        # 통계적으로 이름 아닌 토큰
        assert name_shape_bonus("닭갈비") <= 0.05

    def test_caps_at_0_20(self):
        for name in ("김민수", "박영수", "이수정"):
            assert name_shape_bonus(name) <= 0.20
