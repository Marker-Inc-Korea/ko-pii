from ko_pii.core.types import RiskLevel
from ko_pii.patterns.address import detect


def _detect_list(text):
    return list(detect(text))


class TestAddressPositive:
    def test_full_si_gu_road(self):
        results = _detect_list("서울특별시 강남구 테헤란로 123")
        assert len(results) == 1
        r = results[0]
        assert r.label == "ADDRESS"
        assert r.risk_level == RiskLevel.MEDIUM
        assert r.extra["city"] == "서울특별시"
        assert "강남구" in r.extra["districts"]
        assert r.extra["road"] == "테헤란로"
        assert r.extra["building_number"] == "123"

    def test_gu_only_prefix(self):
        results = _detect_list("강남구 역삼로 45")
        assert len(results) == 1
        assert "강남구" in results[0].extra["districts"]

    def test_with_subbuilding_number(self):
        results = _detect_list("강남구 테헤란로 123-45")
        assert len(results) == 1
        assert results[0].extra["building_number"] == "123-45"

    def test_keyword_anchor_without_prefix(self):
        results = _detect_list("주소: 테헤란로 100")
        assert len(results) == 1
        assert results[0].extra["road"] == "테헤란로"

    def test_dae_ro_form(self):
        results = _detect_list("경기도 성남시 분당구 분당대로 88")
        assert len(results) == 1
        assert results[0].extra["road"] == "분당대로"

    def test_gil_form(self):
        results = _detect_list("강남구 봉은사로 1길 10")
        # 봉은사로 1길 — the road token will match "1길" (the alley)
        assert len(results) == 1


class TestAddressNegative:
    def test_road_without_anchor(self):
        # No 시/도/구 prefix and no 주소 keyword
        assert _detect_list("그냥 테헤란로 100 이런 거") == []

    def test_no_building_number(self):
        assert _detect_list("강남구 테헤란로") == []
