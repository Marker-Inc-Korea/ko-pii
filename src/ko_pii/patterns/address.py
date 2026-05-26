"""주소 (Korean address) detection — 도로명 + 지번 + 대화체 보강.

도로명(road-name) 주소: 로·길·대로 + 건물번호.
지번(jibun) 주소:        동·읍·면·리 + 번지(번지수).
대화체 (loose):          시군구 또는 동 단독 + context keyword (살던/이사/명함 등)

To keep precision high without a full 행정구역 dictionary, we require *either*:
  - A 시/도/시/군/구 token immediately before the road/dong component, OR
  - A "주소" keyword within 20 characters before the match, OR
  - 대화체 강한 anchor (살던/거주/이사/명함/자택 등) + 실제 행정구역 토큰

Legal basis: 개인정보보호법 제2조 (거주지 식별 가능 정보).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.dictionaries.districts import (
    is_country, is_common_dong, is_extra_city,
)

LABEL = "ADDRESS"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

# 단독 행정구역 토큰 — 합성어 부분 매칭 방지 (앞뒤 한글/영숫자 거부)
_PATTERN_ADMIN_TOKEN = re.compile(
    r"(?<![가-힣A-Za-z0-9])([가-힣]{2,6})(?![가-힣A-Za-z0-9])"
)

# 대화체 보강용 anchor — 강한 주거·접촉 정보 신호
_LOOSE_ANCHORS = (
    "주소", "자택", "거주", "본적",
    "사세요", "사신다", "사셨", "사신", "사세",
    "사는", "사니까", "살던", "살아", "살고", "산다", "산대",
    "이사", "이사하", "이사했",
    "명함",
)

# Optional 시·도 + 0~2 시·군·구 (성남시 분당구 같은 2단계) + road + 번지
_PATTERN_ROAD = re.compile(
    r"(?:([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도))\s+)?"
    r"((?:[가-힣]+(?:시|군|구)\s+){0,2})"
    r"([가-힣A-Za-z0-9]+(?:대로|로|길))"
    r"\s+"
    r"([0-9]+(?:-[0-9]+)?)"
)

# 지번 주소: 동/읍/면/리 + 번지수 (0~2 시·군·구 허용)
_PATTERN_JIBUN = re.compile(
    r"(?:([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도))\s+)?"
    r"((?:[가-힣]+(?:시|군|구)\s+){0,2})"
    r"([가-힣]+(?:동|읍|면|리))"
    r"\s+"
    r"([0-9]+(?:-[0-9]+)?)"
    r"(?:\s*번지)?"
)

# 대화체 단독 주소 — 시군구 또는 동 (번지 옵션), 광역 없음
# 강한 anchor keyword 25자 윈도우 내 필수.
_PATTERN_LOOSE = re.compile(
    r"(?<![가-힣])"
    r"([가-힣]{2,}(?:시|군|구|동|읍|면|리))"
    r"(?:\s+([가-힣]+(?:동|읍|면|리)))?"
    r"(?:\s+([0-9]+(?:-[0-9]+)?))?"
    r"(?![가-힣])"
)


def _has_anchor(text: str, start: int, city: str | None, district: str | None) -> str | None:
    if city or district:
        return "prefix"
    window_start = max(0, start - 20)
    if "주소" in text[window_start:start]:
        return "keyword"
    return None


def _has_loose_anchor(text: str, start: int, end: int) -> str | None:
    """대화체 anchor — 매치 *주변* (앞·뒤) 25자 윈도우에서 강한 keyword 검색.

    '살던 응암동에서' (앞) / '구로구로 이사했고' (뒤) 모두 커버.
    """
    head = text[max(0, start - 25): start]
    tail = text[end: min(len(text), end + 12)]
    for kw in _LOOSE_ANCHORS:
        if kw in head or kw in tail:
            return kw
    return None


def _first_district_of(districts_str: str) -> str | None:
    """``"성남시 분당구 "`` → ``"성남시"`` (첫 시·군·구 추출)."""
    if not districts_str:
        return None
    parts = districts_str.split()
    return parts[0] if parts else None


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    from ko_pii.dictionaries.districts import (
        is_province,
        is_district,
        is_valid_province_district,
    )

    for m in _PATTERN_ROAD.finditer(text):
        city = m.group(1)
        districts = (m.group(2) or "").strip()
        # 시·도 prefix 가 있다면 *실제 한국 17개 광역지자체* 인지 검증
        if city and not is_province(city):
            continue
        # (광역+기초) 조합 검증 — 둘 다 있으면 실제 매핑인지 확인
        # 예: "경기도 강남구 ..." → 강남구는 서울 → 거부
        first_district = _first_district_of(districts)
        if city and first_district and not is_valid_province_district(city, first_district):
            continue
        anchor = _has_anchor(text, m.start(), city, districts)
        if anchor is None:
            continue
        span = (m.start(), m.end())
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0).strip(),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.8,
            evidence=["pattern:address_road", f"anchor:{anchor}"],
            legal_basis=LEGAL_BASIS,
            extra={
                "format": "road_name",
                "city": city,
                "districts": districts,
                "road": m.group(3),
                "building_number": m.group(4),
                "category": CATEGORY,
            },
        )

    for m in _PATTERN_JIBUN.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue  # already claimed by road pattern
        city = m.group(1)
        districts = (m.group(2) or "").strip()
        # 시·도 prefix 검증 (위와 동일 — "바티스타밤이라도" 거부)
        if city and not is_province(city):
            continue
        # (광역+기초) 조합 검증
        first_district = _first_district_of(districts)
        if city and first_district and not is_valid_province_district(city, first_district):
            continue
        anchor = _has_anchor(text, m.start(), city, districts)
        if anchor is None:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0).strip(),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.75,
            evidence=["pattern:address_jibun", f"anchor:{anchor}"],
            legal_basis=LEGAL_BASIS,
            extra={
                "format": "jibun",
                "city": city,
                "districts": districts,
                "dong": m.group(3),
                "lot_number": m.group(4),
                "category": CATEGORY,
            },
        )

    # 3) 대화체 단독 주소 — 시군구 또는 동, 강한 keyword anchor 필요
    from ko_pii.dictionaries.districts import ALL_DISTRICTS
    valid_districts = ALL_DISTRICTS
    for m in _PATTERN_LOOSE.finditer(text):
        span = (m.start(), m.end())
        # 기존 jibun/road 매치와 *인접* 한 경우 = 같은 주소의 일부일 가능성 ↑ → skip
        # (예: 가평군 청평면 청평리 45-6 에서 loose 가 "가평군 청평면" 만 떼면
        # jibun 의 "청평리 45-6" 과 인접 → 같은 주소 → loose 거부)
        ADJACENCY = 30
        if any(span[0] < e + ADJACENCY and s - ADJACENCY < span[1] for s, e in seen):
            continue  # adjacent to another address match
        first_token = m.group(1)
        # 첫 토큰이 *실제 한국 행정구역* 인지 확인 (강남구·해운대구·응암동 ...)
        # is_province 거부는 별도 — 광역명은 단독 매치 의도 아님.
        if first_token in {"서울시", "부산시", "대구시", "광주시", "대전시",
                            "울산시", "인천시", "수원시", "고양시", "용인시"}:
            pass  # 광역 약칭 또는 큰 시는 허용 (시군구 사전과 함께 검증)
        elif first_token not in valid_districts:
            continue
        anchor = _has_loose_anchor(text, m.start(), m.end())
        if anchor is None:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0).strip(),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.6,  # 대화체 = 정확도 낮음
            evidence=["pattern:address_loose",
                      f"anchor:context_keyword({anchor})"],
            legal_basis=LEGAL_BASIS,
            extra={
                "format": "loose",
                "first_token": first_token,
                "category": CATEGORY,
            },
        )

    # 4) 단독 행정구역 / 국가명 — anchor 필수 (대화체) + dict 매칭 (LOW risk)
    # 다른 ADDRESS 매치와 인접 (50자 이내) 한 단독 행정구역은 같은 주소의
    # 일부로 보고 emit 거부 (도로명/지번 매칭과 중복 방지)
    from ko_pii.context.particles import strip_trailing_particle
    ADMIN_ALONE_ADJACENCY = 50
    for m in _PATTERN_ADMIN_TOKEN.finditer(text):
        raw_token = m.group(1)
        # 조사 떨기 — "서울로/서울에서/서울이" → "서울"
        token, particle = strip_trailing_particle(raw_token)
        if len(token) < 2:
            continue
        # 국적 접미사 strip ("한국인/미국인" → "한국/미국", country dict 매칭 시만)
        people_suffix = None
        if len(token) >= 3 and token.endswith("인") and is_country(token[:-1]):
            token = token[:-1]
            people_suffix = "인"
        # span 은 stem 부분 (조사·접미사 제외)
        actual_end = m.end() - (len(particle) if particle else 0) - (1 if people_suffix else 0)
        span = (m.start(), actual_end)
        if any(span[0] < e + ADMIN_ALONE_ADJACENCY and s - ADMIN_ALONE_ADJACENCY < span[1]
               for s, e in seen):
            continue
        kind = None
        # 광역 (정식명·약칭·시 약칭)
        if is_province(token) or token in {"강원도", "충청도", "전라도", "경상도", "제주도",
                                            "서울시", "부산시", "대구시", "인천시",
                                            "광주시", "대전시", "울산시"}:
            kind = "province"
        elif is_district(token):
            kind = "district"
        elif is_extra_city(token):
            kind = "city"
        elif is_common_dong(token):
            kind = "dong"
        elif is_country(token):
            kind = "country"
        else:
            continue
        # 대화체 anchor 필수 — 일반 문어체 "25개 자치구 방문" 같은 텍스트 거부.
        # 단 country (국가명) 은 anchor 없이도 emit (KDPII LCP_COUNTRY 의 86%
        # 가 anchor 없는 단독 등장: "한국 남자/미국 친구" 등).
        anchor = _has_loose_anchor(text, m.start(), actual_end)
        if anchor is None and kind != "country":
            continue
        if anchor is None:
            anchor = "country_alone"
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=token,
            start=m.start(),
            end=actual_end,
            risk_level=RiskLevel.LOW,
            confidence=0.7,
            evidence=[f"pattern:admin_alone({kind})", f"dict:{kind}",
                      f"anchor:{anchor}"],
            legal_basis=LEGAL_BASIS,
            extra={
                "format": "admin_alone",
                "admin_kind": kind,
                "category": CATEGORY,
            },
        )
