from ko_pii.patterns.address import detect


def _d(text):
    return list(detect(text))


class TestJibunPositive:
    def test_with_city_prefix(self):
        results = _d("주소: 서울특별시 강남구 역삼동 123")
        assert len(results) == 1
        r = results[0]
        assert r.extra["format"] == "jibun"
        assert r.extra["dong"] == "역삼동"
        assert r.extra["lot_number"] == "123"

    def test_with_eup_myun_ri(self):
        results = _d("주소: 경기도 가평군 청평면 청평리 45-6")
        assert any(r.extra.get("format") == "jibun" for r in results)

    def test_with_bunji_word(self):
        # "123 번지" — explicit 번지 keyword should still match
        results = _d("주소: 서울특별시 강남구 역삼동 123 번지")
        assert any(r.extra.get("format") == "jibun" for r in results)


class TestJibunNegative:
    def test_no_anchor_no_match(self):
        # Without 시/도 prefix or 주소 keyword
        assert _d("역삼동 123 가서 만나자") == []

    def test_road_takes_precedence(self):
        # Road-name version should win when both could match
        text = "서울특별시 강남구 테헤란로 123"
        results = _d(text)
        formats = {r.extra.get("format") for r in results}
        assert "road_name" in formats
