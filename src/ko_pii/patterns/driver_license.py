"""운전면허번호 (Driver License Number) detection.

12-digit format: XX-YY-NNNNNN-CC.
  XX: 지방경찰청 코드 (11~28 range historically assigned)
  YY: 면허 발급 연도 끝 2자리
  NNNNNN: 일련번호
  CC: 위변조 식별번호 (check) — the algorithm is not publicly standardized,
      so this module verifies format and region code only, not the check.

검출 정책:
- 하이픈 있는 형태 (``XX-YY-NNNNNN-CC``) → 패턴만으로 식별 가능
- 하이픈 없는 12자리는 다른 카테고리 (처방번호·날짜 등) 와 충돌 위험 큼
  → **"운전면허" / "면허번호" 키워드 anchor 필수**

Legal basis: 개인정보보호법 시행령 제19조 (고유식별정보의 범위 — 운전면허번호).
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "DRIVER_LICENSE"
LEGAL_BASIS = "개인정보보호법 시행령 제19조"
CATEGORY = "고유식별정보"

# 지방경찰청 region codes (도로교통공단). 11~28 covers the historically
# assigned range including 세종(28). 27 was not in regular use.
_VALID_REGION_CODES: set[str] = {f"{n:02d}" for n in range(11, 29)}

# 하이픈 포함 형태 — 패턴 단독 식별 가능
_PATTERN_HYPHEN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{2})-"
    r"([0-9]{2})-"
    r"([0-9]{6})-"
    r"([0-9]{2})"
    r"(?![0-9])"
)

# 하이픈 없는 12자리 — 키워드 anchor 필수
_PATTERN_NO_HYPHEN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{2})([0-9]{2})([0-9]{6})([0-9]{2})"
    r"(?![0-9])"
)

_KEYWORDS = ("운전면허", "면허번호", "면허증")


def _has_keyword_before(text: str, start: int, window: int = 15) -> str | None:
    head = text[max(0, start - window): start]
    for kw in _KEYWORDS:
        if kw in head:
            return kw
    return None


def _emit(m: re.Match, has_hyphen: bool, kw: str | None) -> DetectionResult:
    region = m.group(1)
    evidence = ["pattern:driver_license", f"region:{region}"]
    if has_hyphen:
        evidence.append("format:hyphenated")
    if kw:
        evidence.append(f"keyword:{kw}")
    return DetectionResult(
        label=LABEL,
        text=m.group(0),
        start=m.start(),
        end=m.end(),
        risk_level=RiskLevel.CRITICAL,
        confidence=0.85,
        evidence=evidence,
        legal_basis=LEGAL_BASIS,
        extra={
            "region_code": region,
            "year_2digit": m.group(2),
            "sequence": m.group(3),
            "check_2digit": m.group(4),
            "format": "hyphenated" if has_hyphen else "compact",
            "category": CATEGORY,
        },
    )


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    for m in _PATTERN_HYPHEN.finditer(text):
        region = m.group(1)
        if region not in _VALID_REGION_CODES:
            continue
        seen.add((m.start(), m.end()))
        yield _emit(m, has_hyphen=True, kw=None)

    for m in _PATTERN_NO_HYPHEN.finditer(text):
        span = (m.start(), m.end())
        if span in seen:
            continue
        region = m.group(1)
        if region not in _VALID_REGION_CODES:
            continue
        kw = _has_keyword_before(text, m.start())
        if kw is None:
            continue
        seen.add(span)
        yield _emit(m, has_hyphen=False, kw=kw)
