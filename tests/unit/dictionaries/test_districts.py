from ko_pii.dictionaries.districts import (
    PROVINCES, ALL_DISTRICTS, ALL_CITIES_GUNS,
    SEOUL_DISTRICTS, METRO_DISTRICTS,
    is_province, is_district, is_admin_unit, normalize_province,
)


class TestProvinces:
    def test_17_widearea_units(self):
        # 1특별시 + 6광역시 + 1특별자치시 + 6도 + 3특별자치도
        assert "서울특별시" in PROVINCES
        for m in ("부산광역시", "대구광역시", "인천광역시", "광주광역시",
                  "대전광역시", "울산광역시"):
            assert m in PROVINCES
        assert "세종특별자치시" in PROVINCES
        for d in ("경기도", "충청북도", "충청남도", "전라남도",
                  "경상북도", "경상남도"):
            assert d in PROVINCES
        for s in ("강원특별자치도", "전북특별자치도", "제주특별자치도"):
            assert s in PROVINCES
        assert len(PROVINCES) == 17

    def test_is_province_accepts_abbreviations(self):
        assert is_province("서울")
        assert is_province("경기")
        assert is_province("강원")
        assert is_province("서울특별시")

    def test_normalize(self):
        assert normalize_province("서울") == "서울특별시"
        assert normalize_province("경기") == "경기도"
        assert normalize_province("강원") == "강원특별자치도"


class TestSeoulDistricts:
    def test_25_districts(self):
        assert len(SEOUL_DISTRICTS) == 25
        for d in ("강남구", "서초구", "송파구", "종로구", "마포구"):
            assert d in SEOUL_DISTRICTS


class TestCitiesGuns:
    def test_gyeonggi_cities(self):
        from ko_pii.dictionaries.districts import GYEONGGI_CITIES
        for c in ("수원시", "성남시", "고양시", "용인시", "화성시"):
            assert c in GYEONGGI_CITIES
        for g in ("연천군", "가평군", "양평군"):
            assert g in GYEONGGI_CITIES

    def test_total_coverage_significant(self):
        # Approximate the 226 figure — we cover all 자치시·군 in the doses
        # (some 자치구 names duplicate across metros so the set is smaller).
        assert len(ALL_CITIES_GUNS) >= 150


class TestDistrictMembership:
    def test_known_districts(self):
        assert is_district("강남구")
        assert is_district("수원시")
        assert is_district("가평군")

    def test_unknown_districts(self):
        assert not is_district("아무구")
        assert not is_district("홍길동")


class TestAdminUnit:
    def test_unified_check(self):
        assert is_admin_unit("서울특별시")
        assert is_admin_unit("강남구")
        assert is_admin_unit("성남시")
        assert not is_admin_unit("홍길동")
