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
from ko_pii.dictionaries.buildings import is_building_name
from ko_pii.dictionaries.legal_dongs import is_legal_dong

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
    r"(?:([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도))\s*)?"
    r"((?:[가-힣]+(?:시|군|구)\s*){0,2})"
    r"([가-힣A-Za-z0-9]+(?:대로|로|길))"
    r"\s*"
    r"([0-9]+(?:-[0-9]+)?)"
)

# 지번 주소: 동/읍/면/리 + 번지수 (0~2 시·군·구 허용)
_PATTERN_JIBUN = re.compile(
    r"(?:([가-힣]+(?:특별시|광역시|특별자치도|특별자치시|도))\s*)?"
    r"((?:[가-힣]+(?:시|군|구)\s*){0,2})"
    r"([가-힣]+(?:동|읍|면|리))"
    r"\s*"
    r"([0-9]+(?:-[0-9]+)?)"
    r"(?:\s*번지)?"
)

# 동호수 확장 패턴 — 주소 직후 "(N동N호)" / "N동 N호" / "N층" / "(아파트명)"
_PATTERN_DETAIL = re.compile(
    r'\s*'
    r'(?:'
    r'(\d+동\s*\d+호)'        # 103동1202호, 103동 1202호
    r'|(\d+동)'               # 103동 (호수 없이)
    r'|(\d+호)'               # 1202호 (동 없이)
    r'|(\d+층)'               # 5층
    r')'
)

# 괄호 안 상세 — "(신정동,롯데캐슬킹덤아파트)" 등
_PATTERN_PAREN_DETAIL = re.compile(
    r'\s*\([가-힣A-Za-z0-9,·\s]+\)'
)

# 건물명/단지명 — 도로명+번호 뒤 상세주소. 임의 고유명사라 사전 대신 위치로 식별.
#  (a) bridge: 뒤에 숫자 동/호/층이 이어지면 양쪽 anchor 로 끼인 건물명
#              ("월드컵북로 396 [누리꿈스퀘어] 12층")
#  (b) tail:   건물 접미사로 끝나는 토큰 — 층 없이도 포함
#              ("테헤란로 152 [강남파이낸스센터]")
# 접미사 목록은 행정안전부 도로명주소 DB(건물명/공동주택명)에서 빈도순으로 보강 가능.
_BLDG_SUFFIX = (
    # 일반 건물 유형
    "빌딩|타워|센터|스퀘어|플라자|프라자|오피스텔|아파트|맨션|하이츠|"
    "캐슬|팰리스|레지던스|펜트하우스|"
    # 아파트/주거 브랜드 (실존 건설사 브랜드)
    "자이|래미안|푸르지오|더샵|아이파크|힐스테이트|디에이치|e편한세상|"
    "위브|센트레빌|롯데캐슬|데시앙|스위첸|꿈에그린|베르디움|리슈빌|코아루|"
    "우미린|한라비발디|효성해링턴|어울림|하늘채|호반써밋|아크로|써밋|주공"
)
_PATTERN_BLDG = re.compile(
    r'\s+[가-힣A-Za-z0-9]{2,}(?=\s+\d+(?:동|호|층))'     # (a) 뒤에 동/호/층
    r'|\s+[가-힣A-Za-z0-9]*(?:' + _BLDG_SUFFIX + r')'     # (b) 건물 접미사
)

# (c) 가제티어 — 접미사 없는 고유 건물명 ("그랑서울" 등). 다음 토큰만 추출해 멤버십 확인.
_PATTERN_NEXT_TOKEN = re.compile(r'\s+([가-힣A-Za-z0-9]+)')

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


def _extend_with_detail(det: DetectionResult, text: str) -> DetectionResult:
    """주소 검출 결과 직후 동호수/층/괄호 상세가 이어지면 span 확장.

    반복 적용: "396 401호 12층" → 401호 잡고 → 12층 잡고 → 끝.
    """
    pos = det.end
    extended_end = det.end

    # 동호수/층 + 건물명 반복 적용
    #   "396 누리꿈스퀘어 12층" → [건물명] 누리꿈스퀘어 → [층] 12층 순차 확장
    #   "396 401호 12층"        → [호] 401호 → [층] 12층
    while True:
        m = _PATTERN_DETAIL.match(text, pos)
        if not m:
            m = _PATTERN_BLDG.match(text, pos)
        if not m:
            # (c) 가제티어 멤버십 — 다음 토큰이 알려진 건물명이면 포함
            mt = _PATTERN_NEXT_TOKEN.match(text, pos)
            if mt and is_building_name(mt.group(1)):
                m = mt
        if not m:
            break
        extended_end = m.end()
        pos = extended_end

    # 괄호 상세 "(신정동,롯데캐슬킹덤아파트)"
    m2 = _PATTERN_PAREN_DETAIL.match(text, pos)
    if m2:
        extended_end = m2.end()

    if extended_end == det.end:
        return det

    from dataclasses import replace
    return replace(det, text=text[det.start:extended_end].strip(), end=extended_end)


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
        det = DetectionResult(
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
        det = _extend_with_detail(det, text)
        span = (det.start, det.end)
        seen.add(span)
        yield det

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
        det = DetectionResult(
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
        det = _extend_with_detail(det, text)
        seen.add((det.start, det.end))
        yield det

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

    # 4) 단독 행정구역 — anchor 필수 (대화체) + dict 매칭 (LOW risk)
    # 국가명은 nationality.py 로 분리 — 여기서는 행정구역만.
    from ko_pii.context.particles import strip_trailing_particle
    ADMIN_ALONE_ADJACENCY = 50
    for m in _PATTERN_ADMIN_TOKEN.finditer(text):
        raw_token = m.group(1)
        token, particle = strip_trailing_particle(raw_token)
        if len(token) < 2:
            continue
        # 국가명은 nationality.py 에서 처리 — 여기서 건너뜀
        if is_country(token) or (len(token) >= 3 and token.endswith("인") and is_country(token[:-1])):
            continue
        actual_end = m.end() - (len(particle) if particle else 0)
        span = (m.start(), actual_end)
        if any(span[0] < e + ADMIN_ALONE_ADJACENCY and s - ADMIN_ALONE_ADJACENCY < span[1]
               for s, e in seen):
            continue
        kind = None
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
        elif is_legal_dong(token):
            # 법정동 가제티어 — 빈출 동(COMMON_DONGS)보다 희귀/모호 → anchor 필수(아래)
            kind = "dong"
        else:
            continue
        anchor = _has_loose_anchor(text, m.start(), actual_end)
        if anchor is None:
            continue
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
