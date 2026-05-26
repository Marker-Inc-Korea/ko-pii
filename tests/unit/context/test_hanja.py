from ko_pii.context.hanja import hanja_to_hangul, has_hanja


class TestHasHanja:
    def test_detection(self):
        assert has_hanja("洪吉童")
        assert has_hanja("홍길동은 大韓民國 사람")
        assert not has_hanja("홍길동")
        assert not has_hanja("Hong Gildong")


class TestHanjaToHangul:
    def test_full_hanja_name(self):
        assert hanja_to_hangul("洪吉童") == "홍길동"

    def test_compound_surname(self):
        assert hanja_to_hangul("南宮") == "남궁"

    def test_mixed_text(self):
        # 한자 일부만 — 매핑된 것만 변환
        result = hanja_to_hangul("洪 사장은")
        assert "홍" in result

    def test_unknown_hanja_preserved(self):
        # 매핑에 없는 한자는 그대로
        result = hanja_to_hangul("☆未知字")
        assert "☆" in result

    def test_empty_string(self):
        assert hanja_to_hangul("") == ""
