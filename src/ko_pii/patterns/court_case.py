"""법원 사건번호 (Court Case Number) detection.

구조: ``YYYY`` + ``부호문자`` + ``일련번호``

부호문자 체계 (대법원「사건별 부호문자의 부여에 관한 예규」):

민사:
  가단  1심 단독        (예: 2020가단578)
  가합  1심 합의
  가소  1심 소액
  나    2심 (항소)
  다    3심 (대법원, 상고)
  카    가압류·가처분 (제재) 보전사건
  차    지급명령
  머    소액심판
  사    사법보좌관

형사:
  고단  1심 단독
  고합  1심 합의
  고정  1심 약식정식
  노    2심 항소
  도    3심 상고
  초    재정
  형보  형사보상
  부    부수처분
  영장  영장 사건

행정:
  구단  1심 단독
  구합  1심 합의
  누    2심 (고등법원)
  두    3심 (대법원)

가사:
  드    1심
  르    2심
  므    3심

기타:
  호    등기·등록사건
  자    영장·결정
  카기   가처분·기타
  보    보전사건

법적 근거: 개인정보보호법 제2조; 민사소송법 제65조 (소송기록 보호).

위험도: MEDIUM (사건번호 자체는 PII 아니지만 당사자 정보 추적 가능).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "COURT_CASE"
LEGAL_BASIS = "개인정보보호법 제2조; 민사소송법 제65조"
CATEGORY = "참조정보"

# 사건별 부호문자 화이트리스트 (대법원 예규 기준 빈출 코드)
_VALID_CASE_CODES: tuple[str, ...] = (
    # 민사
    "가합", "가단", "가소", "나", "다", "카합", "카단", "차", "카기", "머",
    # 형사
    "고합", "고단", "고정", "노", "도", "초", "형보", "고약", "고전",
    # 행정
    "구합", "구단", "누", "두", "구약",
    # 가사
    "드합", "드단", "르", "므", "수단", "수합", "후단", "후합",
    # 등기·기타
    "호", "자", "보", "사", "허", "라", "마", "바",
    # 헌재
    "헌가", "헌나", "헌다", "헌라", "헌마", "헌바",
)

# 우선순위 정렬: 긴 코드부터 매칭되어야 "가합" 이 "가" 보다 먼저 잡힘
_SORTED_CODES = sorted(_VALID_CASE_CODES, key=len, reverse=True)
_CODE_ALTS = "|".join(re.escape(c) for c in _SORTED_CODES)

_PATTERN = re.compile(
    r"(?<![0-9가-힣])"
    r"((?:19|20)\d{2})"          # 연도
    r"(" + _CODE_ALTS + r")"      # 부호문자
    r"(\d{1,6})"                  # 일련번호
    r"(?![0-9가-힣])"
)

_INSTANCE_BY_CODE: dict[str, str] = {
    "가단": "civil_1st_single", "가합": "civil_1st_panel",
    "가소": "civil_1st_small", "나": "civil_2nd", "다": "civil_3rd",
    "고단": "criminal_1st_single", "고합": "criminal_1st_panel",
    "고정": "criminal_1st_summary", "노": "criminal_2nd", "도": "criminal_3rd",
    "구단": "admin_1st_single", "구합": "admin_1st_panel",
    "누": "admin_2nd", "두": "admin_3rd",
    "드합": "family_1st_panel", "드단": "family_1st_single",
    "르": "family_2nd", "므": "family_3rd",
    "차": "payment_order", "카기": "interim_misc",
    "헌가": "constitutional_review", "헌나": "constitutional_complaint",
    "헌마": "constitutional_basic_rights",
}


def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        year = m.group(1)
        code = m.group(2)
        serial = m.group(3)
        # Serial must have at least 1 non-zero digit (일련번호 0 placeholder 거부)
        if int(serial) == 0:
            continue
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.9,
            evidence=[
                "pattern:court_case",
                f"code:{code}",
                f"year:{year}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "year": year,
                "case_code": code,
                "serial": serial,
                "instance": _INSTANCE_BY_CODE.get(code, "unknown"),
                "category": CATEGORY,
            },
        )
