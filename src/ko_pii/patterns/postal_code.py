"""우편번호 (Korean Postal Code) detection.

Two historical formats:
  - 5-digit (2015-08-01 onward): YXXXX — 국가기초구역번호
  - 6-digit legacy (~2015):       XXX-XXX

5자리 첫 2자리 (시·도 코드, 우정사업본부 공개 데이터):
  01~08  서울특별시
  10~18  경기도
  21~23  인천광역시
  24~26  강원특별자치도
  27~29  충청북도
  30     세종특별자치시
  31~33  충청남도
  34~35  대전광역시
  36~40  경상북도
  41~43  대구광역시
  44~45  울산광역시
  46~49  부산광역시
  50~53  경상남도
  54~56  전북특별자치도
  57~59  전라남도
  61~62  광주광역시
  63     제주특별자치도

이 외 범위는 미할당 — FP 위험. 키워드 anchor 와 함께 첫 2자리 화이트리스트
까지 검증.

Legal basis: 개인정보보호법 제2조 (지역 식별 가능 정보).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "POSTAL_CODE"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

# 시·도별 첫 2자리 화이트리스트
_VALID_POSTAL_PREFIXES: frozenset[str] = frozenset(
    [f"{n:02d}" for n in (
        list(range(1, 9))         # 01~08 서울
        + list(range(10, 19))     # 10~18 경기
        + list(range(21, 30))     # 21~29 인천·강원·충북
        + list(range(30, 36))     # 30 세종, 31~33 충남, 34~35 대전
        + list(range(36, 50))     # 36~49 경북·대구·울산·부산
        + list(range(50, 60))     # 50~59 경남·전북·전남
        + [61, 62, 63]            # 광주·제주
    )]
)

_LEGACY = re.compile(
    r"(?<![0-9])"
    r"([0-9]{3}-[0-9]{3})"
    r"(?![0-9])"
)

_NEW_WITH_KEYWORD = re.compile(
    r"(?:우편\s*번호|우편번호|우편)\s*:?\s*"
    r"([0-9]{5})"
    r"(?![0-9])"
)


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    for m in _NEW_WITH_KEYWORD.finditer(text):
        span = (m.start(1), m.end(1))
        if span in seen:
            continue
        code = m.group(1)
        # 첫 2자리 시·도 코드 화이트리스트
        if code[:2] not in _VALID_POSTAL_PREFIXES:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=code,
            start=m.start(1),
            end=m.end(1),
            risk_level=RiskLevel.LOW,
            confidence=1.0,
            evidence=[
                "pattern:postal_code",
                "format:5_digit",
                "keyword:우편번호",
                f"sido_prefix:{code[:2]}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={"value": code, "format": "5_digit", "category": CATEGORY},
        )

    for m in _LEGACY.finditer(text):
        span = (m.start(), m.end())
        if span in seen:
            continue
        # 6자리 레거시도 첫 자리는 1~7 (구 우편번호 체계)
        code = m.group(1)
        first_digit = code[0]
        if first_digit not in "1234567":
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=code,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            evidence=["pattern:postal_code", "format:6_digit_legacy"],
            legal_basis=LEGAL_BASIS,
            extra={"value": code, "format": "6_digit", "category": CATEGORY},
        )
