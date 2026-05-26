import pytest

from ko_pii.generalization.address import generalize_address


def test_city_level():
    assert generalize_address("서울특별시 강남구 테헤란로 123") == "서울특별시"
    assert generalize_address("경기도 성남시 분당구 정자로 1") == "경기도"


def test_district_level():
    assert generalize_address(
        "서울특별시 강남구 테헤란로 123", level="district"
    ) == "서울특별시 강남구"


def test_no_match_passthrough():
    assert generalize_address("그냥 문장") == "그냥 문장"


def test_unknown_level_raises():
    with pytest.raises(ValueError):
        generalize_address("서울특별시", level="dong")
