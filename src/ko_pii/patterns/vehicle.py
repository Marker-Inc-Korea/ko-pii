"""자동차 등록번호 (Vehicle License Plate) detection.

Korean plate format (post-2004):
  NN[가-힣] NNNN  or  NNN[가-힣] NNNN
  ─ 2 or 3 digit prefix (앞자리, 차종)
  ─ 1 Korean character (용도 코드 — 화이트리스트로 검증)
  ─ 4 digit suffix (뒷자리, 일련번호)

용도 한글 화이트리스트 (자동차관리법 시행규칙 별표 7):

  자가용 (32자): 가나다라마 거너더러머버서어저 고노도로모보소오조 구누두루무부수우주
  영업용 (4자):  바 사 아 자 (택시·버스·화물·렌트)
  배달·택배(1자): 배
  렌터카 (3자):  하 허 호
  외교용 (7자):  외 영 준 협 대 (+ 임시 변형)
  군용 (5자):    국 합 육 해 공

총 약 50개 한글 문자만 유효 — 그 외 한글이 들어가면 FP 가 거의 확실.

Legal basis: 개인정보보호법 제2조 (차량 소유자 식별 가능 정보).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "VEHICLE"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

# 한글 용도 코드 화이트리스트
_VEHICLE_HANGUL: frozenset[str] = frozenset({
    # 자가용 (비사업용) 32자 — 자동차관리법 시행규칙 별표7
    "가", "나", "다", "라", "마",
    "거", "너", "더", "러", "머", "버", "서", "어", "저",
    "고", "노", "도", "로", "모", "보", "소", "오", "조",
    "구", "누", "두", "루", "무", "부", "수", "우", "주",
    # 영업용 (택시·버스·화물 등)
    "바", "사", "아", "자",
    # 배달·택배
    "배",
    # 렌터카 (2013~)
    "하", "허", "호",
    # 외교용
    "외", "영", "준", "협", "대",
    # 군용
    "국", "합", "육", "해", "공",
})


def _vehicle_purpose(hangul: str) -> str:
    """Classify the 1-char purpose code."""
    if hangul in {"바", "사", "아", "자"}: return "commercial"
    if hangul == "배": return "delivery"
    if hangul in {"하", "허", "호"}: return "rental"
    if hangul in {"외", "영", "준", "협", "대"}: return "diplomatic"
    if hangul in {"국", "합", "육", "해", "공"}: return "military"
    return "private"


_PATTERN = re.compile(
    r"(?<![0-9가-힣])"
    r"([0-9]{2,3})\s?([가-힣])\s?([0-9]{4})"
    r"(?![0-9])"  # allow Korean particles to follow ("12가3456의 차량")
)

# 차량번호 뒤에 따라오면 차량 X — 한국어 수량·통화 단위어
_FOLLOWING_UNIT_REJECT: tuple[str, ...] = (
    "원", "달러", "엔", "위안", "유로", "파운드", "프랑",
    "억", "만", "천", "백", "조",
    "%", "퍼센트", "퍼센트포인트",
    "포인트", "포",
    "건", "건수", "명", "년", "월", "일", "시간", "분", "초",
    "톤", "kg", "g", "m", "km", "mm",
)


def _has_unit_after(text: str, end: int) -> str | None:
    """차량번호 뒤에 한국어 수량/통화 단위가 따라오면 차량 아님."""
    tail = text[end: end + 8].lstrip()
    for unit in _FOLLOWING_UNIT_REJECT:
        if tail.startswith(unit):
            return unit
    return None


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        purpose_char = m.group(2)
        # 용도 한글 화이트리스트 — 그 외 한글은 FP
        if purpose_char not in _VEHICLE_HANGUL:
            continue
        suffix = m.group(3)
        # 뒷 4자리 0000 은 placeholder/시범 번호 — 실제 차량 아님
        if suffix == "0000":
            continue
        # 뒤에 한국어 수량·통화 단위 → 차량 아님 ("291조9000억 원" 등)
        unit = _has_unit_after(text, m.end())
        if unit:
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            evidence=[
                "pattern:vehicle",
                f"purpose:{_vehicle_purpose(purpose_char)}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "prefix": m.group(1),
                "purpose_char": purpose_char,
                "purpose": _vehicle_purpose(purpose_char),
                "suffix": suffix,
                "category": CATEGORY,
            },
        )
