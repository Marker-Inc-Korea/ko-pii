"""조합 사전 테스트 — (광역+기초) / (부처+직급) 매핑 검증."""
from ko_pii.dictionaries.agency_titles import (
    is_valid_agency_title,
    specialized_agencies_for,
    valid_titles_for,
)
from ko_pii.dictionaries.districts import (
    PROVINCE_DISTRICTS,
    districts_of,
    is_valid_province_district,
)


# ─────────────────────────────────────────────────────────────────────
# (광역 + 기초) 조합
# ─────────────────────────────────────────────────────────────────────

class TestProvinceDistrictMapping:
    def test_seoul_districts_correct(self):
        # 강남구는 서울에 있음
        assert is_valid_province_district("서울특별시", "강남구")
        assert is_valid_province_district("서울특별시", "종로구")
        assert is_valid_province_district("서울특별시", "송파구")

    def test_seoul_strangerejected(self):
        # 강남구가 경기도? 아님
        assert not is_valid_province_district("경기도", "강남구")
        # 성남시가 서울? 아님 — 경기도에 있음
        assert not is_valid_province_district("서울특별시", "성남시")

    def test_gyeonggi_cities(self):
        assert is_valid_province_district("경기도", "성남시")
        assert is_valid_province_district("경기도", "수원시")
        assert is_valid_province_district("경기도", "고양시")
        assert is_valid_province_district("경기도", "가평군")

    def test_busan_districts(self):
        assert is_valid_province_district("부산광역시", "해운대구")
        assert is_valid_province_district("부산광역시", "기장군")
        # 강남구는 부산에 없음 (서울)
        assert not is_valid_province_district("부산광역시", "강남구")

    def test_abbreviation_works(self):
        # 광역 약칭도 매핑됨
        assert is_valid_province_district("서울", "강남구")
        assert is_valid_province_district("경기", "성남시")

    def test_empty_inputs(self):
        assert not is_valid_province_district("", "강남구")
        assert not is_valid_province_district("서울특별시", "")
        assert not is_valid_province_district("", "")

    def test_unknown_province_rejected(self):
        # 가짜 광역 — "바티스타도" 같은 거 거부
        assert not is_valid_province_district("바티스타밤이라도", "강남구")

    def test_districts_of_returns_set(self):
        seoul_dists = districts_of("서울특별시")
        assert "강남구" in seoul_dists
        assert "성남시" not in seoul_dists  # 성남시는 경기도

    def test_all_17_provinces_have_mapping(self):
        # 17 광역 모두 매핑 존재 (세종은 0 districts)
        assert len(PROVINCE_DISTRICTS) >= 17
        # 세종 제외하고는 모두 1개 이상의 기초자치단체
        for province, districts in PROVINCE_DISTRICTS.items():
            if "세종" not in province:
                assert len(districts) > 0, f"{province} 에 기초자치단체 없음"


# ─────────────────────────────────────────────────────────────────────
# (기관 + 직급) 조합
# ─────────────────────────────────────────────────────────────────────

class TestAgencyTitleMapping:
    def test_common_titles_work_anywhere(self):
        # 일반직 직급은 모든 부처에서 유효
        assert is_valid_agency_title("기획재정부", "사무관")
        assert is_valid_agency_title("환경부", "사무관")
        assert is_valid_agency_title("외교부", "주무관")
        assert is_valid_agency_title("법무부", "과장")

    def test_specialized_titles_restricted(self):
        # 치안총감은 경찰청만
        assert is_valid_agency_title("경찰청", "치안총감")
        assert not is_valid_agency_title("환경부", "치안총감")
        assert not is_valid_agency_title("기획재정부", "치안총감")

    def test_specialized_titles_propagate_to_parent_ministry(self):
        # 행안부 산하 외청 (경찰청) 직급은 행안부에서도 유효
        assert is_valid_agency_title("행정안전부", "치안총감")
        assert is_valid_agency_title("행정안전부", "소방총감")

    def test_court_titles(self):
        assert is_valid_agency_title("대법원", "대법원장")
        assert is_valid_agency_title("대법원", "대법관")
        assert not is_valid_agency_title("기획재정부", "대법관")

    def test_diplomatic_titles(self):
        assert is_valid_agency_title("외교부", "대사")
        assert is_valid_agency_title("외교부", "1등서기관")
        assert not is_valid_agency_title("환경부", "대사")

    def test_military_titles_in_mnd(self):
        # 국방부에서 군 계급 유효
        assert is_valid_agency_title("국방부", "대장")
        assert is_valid_agency_title("국방부", "원수")
        assert not is_valid_agency_title("기획재정부", "대장")

    def test_specialized_agencies_reverse(self):
        # 직책 → 기관 역매핑
        agencies = specialized_agencies_for("치안총감")
        assert "경찰청" in agencies

        agencies = specialized_agencies_for("대법원장")
        assert "대법원" in agencies

        agencies = specialized_agencies_for("대사")
        assert "외교부" in agencies

    def test_valid_titles_includes_common(self):
        titles = valid_titles_for("기획재정부")
        assert "장관" in titles
        assert "사무관" in titles
        assert "과장" in titles
        # 특정직은 부처와 무관하면 미포함
        assert "치안총감" not in titles


# ─────────────────────────────────────────────────────────────────────
# 통합: ADDRESS 검출기에 조합 검증 적용 확인
# ─────────────────────────────────────────────────────────────────────

class TestAddressCombinationValidation:
    def test_invalid_combination_rejected(self):
        from ko_pii.patterns.address import detect
        # "경기도 강남구" — 강남구는 서울이므로 거부
        results = list(detect("서류는 경기도 강남구 테헤란로 100 으로 발송"))
        assert not results

    def test_valid_combination_accepted(self):
        from ko_pii.patterns.address import detect
        # "경기도 성남시" — 유효
        results = list(detect("경기도 성남시 분당구 정자로 1"))
        assert len(results) == 1

    def test_seoul_gangnam_correct(self):
        from ko_pii.patterns.address import detect
        results = list(detect("서울특별시 강남구 테헤란로 152"))
        assert len(results) == 1

    def test_fake_province_rejected(self):
        from ko_pii.patterns.address import detect
        # "바티스타밤이라도" 같은 가짜 시·도 → 이미 이전 fix 로 거부
        results = list(detect("바티스타밤이라도 나왔으면 1점줄 영화"))
        assert not results
