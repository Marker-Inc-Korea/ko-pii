"""필지고유번호 (PNU, Parcel Number) detection — 19자리 결정적 PII.

구조 (국토교통부 / 국가공간정보포털):
  [시도 2][시군구 3][읍면동 3][리 2] [필지구분 1] [본번 4] [부번 4] = 19 자리

  - 행정구역 10 자리 = 법정동코드 (1자리 행정구역 + 9자리 코드 합)
  - 필지구분: 1=일반번지, 2=산번지, 3~8=가번지/블록번지 변형, 9=기타
  - 본번 4 자리 (0-padded, 1~9999)
  - 부번 4 자리 (0-padded, 0~9999)

검출 정확도 향상:
  1. 시도 코드 (앞 2자리) 가 11~50 범위 (행정안전부 표준코드 범위)
  2. 필지구분 1자리가 1~9
  3. 본번이 0000 아님 (실제 토지는 본번 1 이상)

법적 근거: 「공간정보의 구축 및 관리 등에 관한 법률」, 개인정보보호법 제2조
  (토지 소유자와 결합 시 식별 가능).

Legal basis (extra["category"] = "참조정보"): 토지 자체는 PII 가 아니지만 소유자
등기 정보와 결합 시 식별·재산 추정 가능. STRICT 모드에서 REVIEW.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "PNU"
LEGAL_BASIS = "공간정보의 구축 및 관리 등에 관한 법률; 개인정보보호법 제2조"
CATEGORY = "참조정보"

# 19자리 숫자, 주변에 다른 숫자가 없는 boundary
_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{19})"
    r"(?![0-9])"
)

# 시도 행정구역 코드 (행정안전부 표준)
# 11=서울 21=부산 22=대구 23=인천 24=광주 25=대전 26=울산 29=세종
# 31=경기 32=강원 33=충북 34=충남 35=전북 36=전남 37=경북 38=경남 39=제주
_VALID_SIDO_CODES: frozenset[str] = frozenset({
    "11", "21", "22", "23", "24", "25", "26", "29",
    "31", "32", "33", "34", "35", "36", "37", "38", "39",
    # 일부 자료에서 사용하는 변형 코드 — 변경 이력 보존용
    "41", "42", "43", "44", "45", "46", "47", "48", "50",
})


def _is_valid_pnu(digits: str) -> tuple[bool, dict]:
    if len(digits) != 19:
        return False, {}
    sido = digits[0:2]
    if sido not in _VALID_SIDO_CODES:
        return False, {}
    sigungu = digits[2:5]
    eupmyeondong = digits[5:8]
    ri = digits[8:10]
    parcel_type = digits[10]
    bonbun = digits[11:15]
    bubun = digits[15:19]

    # 필지구분 1~9
    if parcel_type == "0":
        return False, {}
    # 본번은 0001 이상이어야 의미가 있음 (실제 토지)
    if bonbun == "0000":
        return False, {}

    return True, {
        "sido_code": sido,
        "sigungu_code": sigungu,
        "eupmyeondong_code": eupmyeondong,
        "ri_code": ri,
        "parcel_type": parcel_type,
        "bonbun": int(bonbun),
        "bubun": int(bubun),
        "is_san": parcel_type == "2",
    }


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        digits = m.group(1)
        ok, info = _is_valid_pnu(digits)
        if not ok:
            continue
        yield DetectionResult(
            label=LABEL,
            text=digits,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            evidence=[
                "pattern:pnu",
                f"sido:{info['sido_code']}",
                f"parcel_type:{info['parcel_type']}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "category": CATEGORY,
                **info,
            },
        )
