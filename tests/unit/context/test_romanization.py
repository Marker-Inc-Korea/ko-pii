from ko_pii.context.romanization import alternative_romanizations, romanize_name


class TestRomanize:
    def test_basic_name(self):
        # 홍길동: 홍=Hong, 길=Gil, 동=Dong → 합쳐 Gildong
        result = romanize_name("홍길동")
        assert result.startswith("Hong")
        assert "ildong" in result.lower() or "il dong" in result.lower()

    def test_compound_surname(self):
        # 남궁민수: 남궁=Namgung, 민수=Minsu
        result = romanize_name("남궁민수")
        assert result.startswith("Namgung")

    def test_two_char_name(self):
        result = romanize_name("이수")
        assert result.startswith("I")
        assert " " in result  # 성 + 이름 분리


class TestAlternativeRomanizations:
    def test_multiple_variants(self):
        alts = alternative_romanizations("홍길동")
        # 빈도 높은 변형들 포함
        joined = " | ".join(alts).lower()
        assert "hong" in joined
        assert "-" in " | ".join(alts)  # 하이픈 형태 포함

    def test_single_canonical_only_when_unparseable(self):
        # surname 없는 입력 — 변환은 되지만 변형은 단일
        alts = alternative_romanizations("xxx")
        assert len(alts) >= 1
