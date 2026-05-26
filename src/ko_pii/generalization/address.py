"""주소 일반화 — 상세 주소 → 상위 행정구역.

입력은 검출 결과 또는 임의 한국 주소 문자열. 시·도까지만 남기거나, 시·군·구
까지 남기는 두 모드를 지원.
"""
from __future__ import annotations

import re

_CITY_PATTERN = re.compile(
    r"([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도))"
)
_DISTRICT_PATTERN = re.compile(
    r"([가-힣]+(?:시|군|구))"
)


def generalize_address(addr: str, level: str = "city") -> str:
    """Trim ``addr`` to the first 시·도 (``"city"``) or 시·군·구 (``"district"``).

    Falls back to the input on no match.
    """
    if level not in {"city", "district"}:
        raise ValueError(f"Unknown level: {level}")
    city = _CITY_PATTERN.search(addr)
    if level == "city":
        return city.group(1) if city else addr
    # Search for 시·군·구 strictly after the 시·도 to avoid matching
    # the same token ("서울특별시" also ends with 시).
    search_from = city.end() if city else 0
    district = _DISTRICT_PATTERN.search(addr, search_from)
    if city and district:
        return f"{city.group(1)} {district.group(1)}"
    if city:
        return city.group(1)
    if district:
        return district.group(1)
    return addr
