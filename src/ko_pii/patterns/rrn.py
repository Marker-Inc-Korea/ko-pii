"""주민등록번호 (Resident Registration Number) detection.

Detection criteria, in order:
  1. Pattern: 13 ASCII digits with an optional hyphen between the 6th and 7th
     digit, with no surrounding digits (prevents matches inside longer numeric
     runs such as credit cards).
  2. Gender/century digit (7th) must indicate a Korean national: {1, 2, 3, 4,
     9, 0}. Foreigner codes {5, 6, 7, 8} are handled by ko_pii.patterns.frn.
  3. Date validity: digits 1..6 must form a real calendar date once the
     century is decoded from the 7th digit.
  4. Checksum: if it passes the standard weighted-sum check, confidence = 1.0;
     otherwise the candidate is still emitted with reduced confidence (0.7),
     because post-2020 RRNs may not satisfy the checksum.

Legal basis: 개인정보보호법 제24조의2 (고유식별정보, 주민등록번호 처리 제한).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.checksum.rrn_checksum import is_valid_checksum
from ko_pii.checksum.corp_reg_checksum import (
    is_valid_checksum as _is_valid_corp_checksum,
)
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "RRN"
LEGAL_BASIS = "개인정보보호법 제24조의2"
CATEGORY = "고유식별정보"

_PATTERN = re.compile(
    r"(?<![0-9])"
    r"([0-9]{6})"
    # 구분자: 하이픈/점/공백 최대 2자(셀 줄바꿈 래핑 '-\n' 등) + 공백으로 감싼
    # 구분자 ' - '(서식 표기) 허용. 순수 공백 3자 이상은 비허용(표 칼럼 FP 방지).
    r"(?:\s?[-./]\s?|[-./\s]{0,2})"
    r"([0-9]{7})"
    r"(?![0-9])"
)

# PDF 서식용: 앞에 1자리 숫자(관계코드 등)가 붙은 패턴
# "1951230-1850431" → 앞 1은 관계코드, 951230-1850431이 RRN
_PATTERN_PREFIXED = re.compile(
    r"(?<![0-9])"
    r"[0-9]"             # 1자리 prefix (관계코드 등)
    r"([0-9]{6})"
    r"(?:\s?[-./]\s?|[-./\s]{0,2})"   # 기본 패턴과 동일 구분자 규칙
    r"([0-9]{7})"
    r"(?![0-9])"
)

_CENTURY_BY_GENDER_DIGIT: dict[int, int] = {
    1: 1900, 2: 1900,
    3: 2000, 4: 2000,
    9: 1800, 0: 1800,
}


def _decode_birth_date(yymmdd: str, gender_digit: int) -> date | None:
    century_base = _CENTURY_BY_GENDER_DIGIT.get(gender_digit)
    if century_base is None:
        return None
    try:
        return date(
            century_base + int(yymmdd[0:2]),
            int(yymmdd[2:4]),
            int(yymmdd[4:6]),
        )
    except ValueError:
        return None


def _emit(m: re.Match, offset: int = 0) -> DetectionResult | None:
    """공통 RRN 검출 로직. offset = 매치 내에서 front 시작 위치 보정."""
    front, back = m.group(1), m.group(2)
    gender_digit = int(back[0])
    birth = _decode_birth_date(front, gender_digit)
    if birth is None:
        return None

    # 미래 생년월일은 실존 인물의 RRN일 수 없음 → 미방출.
    # 880·881·888 로 시작하는 한국 GS1/EAN-13 바코드(예: 8801234567890)가
    # 7번째 자리=3/4 일 때 2000년대 century 로 디코딩되어 2088년 등
    # 미래 일자를 만드는 FP 차단. 실제 RRN(생년 ≤ 현재년)은 영향 없음.
    if birth > date.today():
        return None

    digits_only = front + back
    checksum_ok = is_valid_checksum(digits_only)

    # RRN 체크섬 실패 + 성별자리(7번째)=0 + 법인 체크섬 통과 → 법인등록번호로 판단해
    # RRN 미방출. (설계 D-003: 130111-0006246·191211-0006639 류 CORP_REG.)
    # 성별자리 0 은 법인번호 종류코드의 전형값이자 1800년대 RRN(실질 무의미)이라,
    # 실사용 RRN(성별 1~8)은 법인 체크섬을 우연히 통과해도 그대로 RRN 으로 보호.
    if not checksum_ok and back[0] == "0" and _is_valid_corp_checksum(digits_only):
        return None

    # GS1 한국 EAN-13 바코드(880~ 시작, 무구분자, 체크섬 불일치)는 RRN 이 아니다.
    # 진짜 88년생 RRN 은 체크섬을 통과(checksum_ok)하므로 영향 없음(recall-safe).
    real = m.group(0)[offset:]
    if not checksum_ok and digits_only.startswith("880") and real == digits_only:
        return None

    evidence = ["pattern:rrn", f"date_valid:{birth.isoformat()}"]
    if checksum_ok:
        evidence.append("checksum:valid")
        confidence = 1.0
    else:
        evidence.append("checksum:invalid_or_post_2020")
        confidence = 0.7

    # span은 prefix를 제외한 실제 RRN 부분
    real_text = m.group(0)[offset:]
    return DetectionResult(
        label=LABEL,
        text=real_text,
        start=m.start() + offset,
        end=m.end(),
        risk_level=RiskLevel.CRITICAL,
        confidence=confidence,
        evidence=evidence,
        legal_basis=LEGAL_BASIS,
        extra={
            "front": front,
            "back": back,
            "birth_date": birth.isoformat(),
            "gender_digit": gender_digit,
            "checksum_valid": checksum_ok,
            "category": CATEGORY,
        },
    )


def detect(text: str) -> Iterator[DetectionResult]:
    """Yield a DetectionResult for each plausible RRN found in *text*."""
    seen: set[tuple[int, int]] = set()

    # 기본 패턴
    for m in _PATTERN.finditer(text):
        result = _emit(m)
        if result is not None:
            seen.add((result.start, result.end))
            yield result

    # PDF prefix 패턴 (관계코드 등 1자리 숫자 뒤 RRN)
    for m in _PATTERN_PREFIXED.finditer(text):
        result = _emit(m, offset=1)
        if result is not None and (result.start, result.end) not in seen:
            seen.add((result.start, result.end))
            yield result
