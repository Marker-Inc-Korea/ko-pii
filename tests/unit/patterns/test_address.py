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


class TestAddressBuildingDetail:
    """건물명/동·호·층 상세 확장 (도로명+번호 뒤)."""

    def _addr(self, text):
        return [r.text for r in _detect_list(text) if r.label == "ADDRESS"]

    def test_floor_after_number(self):
        assert self._addr("서울특별시 마포구 월드컵북로 396 12층") == [
            "서울특별시 마포구 월드컵북로 396 12층"
        ]

    def test_dong_ho_chain(self):
        assert self._addr("경기도 성남시 분당구 판교역로 235 103동 1502호") == [
            "경기도 성남시 분당구 판교역로 235 103동 1502호"
        ]

    def test_building_name_bridged_to_floor(self):
        # 건물명이 번호와 층 사이에 끼면 양쪽 anchor 로 함께 잡힌다
        assert self._addr("서울특별시 마포구 월드컵북로 396 누리꿈스퀘어 12층") == [
            "서울특별시 마포구 월드컵북로 396 누리꿈스퀘어 12층"
        ]

    def test_building_suffix_tail(self):
        # 브랜드 접미사(스퀘어/래미안 등)로 끝나면 층 없이도 포함
        assert self._addr("서울 강남구 테헤란로 152 강남파이낸스센터") == [
            "강남구 테헤란로 152 강남파이낸스센터"
        ]
        assert self._addr("서울 강남구 테헤란로 152 래미안 30층") == [
            "강남구 테헤란로 152 래미안 30층"
        ]

    def test_gazetteer_building_name(self):
        # 접미사 없는 고유 건물명은 가제티어 멤버십으로 포함
        assert self._addr("서울 종로구 종로 33 그랑서울 5층") == [
            "종로구 종로 33 그랑서울 5층"
        ]

    def test_unknown_word_not_overextended(self):
        # 가제티어에 없고 접미사도 아니고 뒤에 층도 없으면 확장 안 함
        assert self._addr("서울 강남구 테헤란로 152 본사에서 회의") == [
            "강남구 테헤란로 152"
        ]

    def test_gazetteer_is_populated(self):
        # K-apt 단지명으로 가제티어가 시드 수준이 아니라 실제로 채워져 있어야 함
        from ko_pii.dictionaries.buildings import building_names
        assert len(building_names()) > 1000


class TestLegalDongAnchorConditional:
    """법정동 가제티어 — 강한 anchor 있을 때만 emit (FP 방지)."""

    def _addr(self, text):
        return [r.text for r in _detect_list(text) if r.label == "ADDRESS"]

    def test_legal_dong_with_anchor(self):
        # 희귀 법정동 + 주거 anchor → 검출
        assert "갈월동" in str(self._addr("갈월동으로 이사했어"))

    def test_legal_dong_without_anchor(self):
        # anchor 없으면 단독 동은 emit 안 함
        assert self._addr("애월읍 특산물이 유명하다") == []

    def test_common_word_dong_excluded(self):
        # 일반어 충돌(변동/관리/거리 등)은 가제티어에서 제외 → anchor 있어도 동으로 안 잡힘
        from ko_pii.dictionaries.legal_dongs import is_legal_dong
        assert not is_legal_dong("변동") and not is_legal_dong("관리")

    def test_legal_dongs_populated(self):
        from ko_pii.dictionaries.legal_dongs import legal_dongs
        assert len(legal_dongs()) > 5000
