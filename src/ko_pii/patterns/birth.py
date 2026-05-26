"""생년월일 (Date of Birth) detection.

지원 포맷:
  - 1988년 1월 1일 / 1988년 01월 01일
  - 1988.1.1 / 1988.01.01 / 1988-01-01 / 1988/01/01
  - 88년 1월 1일 / 88.1.1 (2자리 연도)
  - 880101 (RRN 앞 6자리 — 키워드 anchor 필수)
  - 88년생 / 1988년생

검증:
  - 연도: 1900 ~ 현재 년도
  - 월: 1-12
  - 일: 1-31 (월별 + 윤년 검증)

키워드 anchor (단순 날짜 vs 생년월일 구분):
  - "생년월일" / "생일" / "출생" / "출생일" / "DOB" / "Date of Birth"
  - "년생" suffix (88년생 = 1988년생)
  - 키워드 없는 단순 날짜 (예: "2024년 4월 15일 회의") 는 검출 안 함

Legal basis: 개인정보보호법 제2조; 생년월일은 RRN 앞자리와 동일하여
강한 식별성을 가짐. 다른 정보와 결합 시 즉시 식별 가능 = quasi-identifier.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "DT_BIRTH"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "준식별자"

# 한국어 키워드 anchor — 25자 윈도우 (대화체 변형 포함)
_KEYWORDS = (
    "생년월일", "생일", "출생일", "출생", "탄생",
    "태어난", "태어났", "태어나",
    "DOB", "Date of Birth", "Birth Date", "birthday",
)

# 명시적 비-생일 일자 키워드 — 직전에 있으면 DT_BIRTH 거부 (공문서에 흔함)
# 보도자료 "배포일자", 회의 "회의일자", 결재 "시행일자", 인사 "발령일자" 등.
_NON_BIRTH_KEYWORDS = (
    "선고일자", "선고일", "심사일자", "심사일", "처리일자", "처리일",
    "회의일자", "회의일", "시행일자", "시행일", "공포일자", "공포일",
    "배포일자", "배포일", "발령일자", "발령일", "접수일자", "접수일",
    "회신일자", "회신일", "통보일자", "통보일", "처분일자", "처분일",
    "발급일자", "발급일", "유효기간", "평가기간", "계약기간",
    "감사기간", "출동일자", "종결일자", "작성일자", "발생일시",
    "발생일", "발효일", "효력 발생일", "결재일자", "결재일",
    "회계기간", "회계연도", "기준일",
)


def _has_non_birth_keyword_before(text: str, start: int, window: int = 15) -> bool:
    head = text[max(0, start - window): start]
    return any(kw in head for kw in _NON_BIRTH_KEYWORDS)

# 패턴 1: YYYY년 M월 D일 / YYYY년 MM월 DD일
_PATTERN_KOREAN = re.compile(
    r"(?<![0-9])"
    r"(\d{4}|\d{2})"
    r"\s*년\s*"
    r"(\d{1,2})"
    r"\s*월\s*"
    r"(\d{1,2})"
    r"\s*일"
)

# 패턴 2: YYYY.M.D / YYYY-MM-DD / YYYY/MM/DD / YY.MM.DD (구분자 통일)
_PATTERN_NUMERIC = re.compile(
    r"(?<![0-9])"
    r"(\d{2,4})"
    r"([./-])"
    r"(\d{1,2})"
    r"\2"
    r"(\d{1,2})"
    r"(?![0-9])"
)

# 패턴 3: YY년생 / YYYY년생 (연도만)
_PATTERN_BIRTH_YEAR = re.compile(
    r"(?<![0-9])"
    r"(\d{2,4})"
    r"\s*년\s*생"
)


def _normalize_year(year: int) -> int | None:
    """2자리 연도를 4자리로 정규화. 1900 ~ 현재년도 범위만 허용."""
    current_year = date.today().year
    if year < 100:
        # 2자리: 25 이하면 20XX, 그 이상은 19XX
        year = 2000 + year if year <= current_year % 100 else 1900 + year
    if 1900 <= year <= current_year:
        return year
    return None


def _valid_date(year: int, month: int, day: int) -> bool:
    """월/일 + 윤년 검증."""
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _has_keyword_before(text: str, start: int, window: int = 25) -> str | None:
    head = text[max(0, start - window): start]
    for kw in _KEYWORDS:
        if kw in head:
            return kw
    return None


def _has_birth_marker_after(text: str, end: int) -> bool:
    """패턴 매치 끝 뒤에 '생' (예: "88년생") 이 붙어있는지."""
    tail = text[end: end + 2]
    return tail.startswith("생")


# 풀네임 인접 정규식 — 한국 성씨 + 1-3자 이름 (간략판)
_PERSON_NEAR_PATTERN = re.compile(
    r"[가-힣]{2,4}"
    r"(?:이에요|이라|입니다|이고|이며|이요|예요|이니|입니다\.|이|는|은|가|와|과)?"
)


# 한국어 조사·동사 활용 종결 — 풀네임 끝 글자가 이걸로 끝나면 일반 어휘
_PARTICLES = frozenset("는은이가도을를의에로와과만")
_VERB_ENDINGS = frozenset("다네요지까려면고잖야아어라사세")  # 동사·형용사 활용

# 이름 끝에 잘 안 오는 글자 (안전망)
_NON_NAME_FINAL = _PARTICLES | _VERB_ENDINGS


def _has_person_context_nearby(text: str, start: int, end: int, window: int = 15) -> bool:
    """매치 *주변* 15자 윈도우에 *풀네임 인명* 패턴이 있는지.

    조건:
      1) 정확히 3-4자 한글 토큰
      2) 첫 글자가 성씨
      3) 마지막 글자가 조사 (는/은/이/가/도/...) 가 *아님* — "회의는" 거부
      4) common_word·title 아님

    "이계용, 88년 7월 4일" → "이계용" = "용" (조사 X) → True
    "96년 7월 29일 조윤경" → "조윤경" → True
    "회의는 2024년 4월 15일" → "회의는" → "는" 조사 → False
    """
    from ko_pii.dictionaries.surnames import surname_prefix_len
    from ko_pii.dictionaries.common_words import is_common_word
    from ko_pii.dictionaries.titles import is_title
    from ko_pii.context.particles import strip_trailing_particle
    head = text[max(0, start - window): start]
    tail = text[end: end + window]
    for chunk in (head, tail):
        # 3~5자 한글 토큰 — 조사 stripping 까지 시도 (이하이가 → 이하이)
        for m in re.finditer(r"(?<![가-힣])([가-힣]{3,5})(?![가-힣])", chunk):
            raw = m.group(1)
            # 조사 떨기 — 예: "이하이가" → ("이하이", "가")
            token, _ = strip_trailing_particle(raw)
            if len(token) < 2 or len(token) > 4:
                continue
            if surname_prefix_len(token) == 0:
                continue
            if token[-1] in _NON_NAME_FINAL:  # 조사·동사 활용 어미 = 일반 단어
                continue
            # 추가 안전망: 토큰 중 *중간* 글자에 흔한 한자어 음절 ('율/론/론/도/책' 등)
            # 이 들어 있으면 이름이라기보다 일반어. 단순화: 토큰의 이름끝 음절 사전
            # (name_final) 확인.
            from ko_pii.patterns.person import _NAME_FINAL_SYLLABLES
            if token[-1] not in _NAME_FINAL_SYLLABLES:
                continue
            if is_common_word(token) or is_title(token):
                continue
            return True
    return False


def detect(text: str) -> Iterator[DetectionResult]:
    seen: set[tuple[int, int]] = set()

    # 패턴 1: 한국어 (YYYY년 M월 D일)
    for m in _PATTERN_KOREAN.finditer(text):
        year_raw = int(m.group(1))
        year = _normalize_year(year_raw)
        if year is None:
            continue
        month, day = int(m.group(2)), int(m.group(3))
        if not _valid_date(year, month, day):
            continue
        # 명시적 비-생일 키워드 ("선고일자/시행일자/배포일자" 등) 직전 → 거부
        if _has_non_birth_keyword_before(text, m.start()):
            continue
        kw = _has_keyword_before(text, m.start())
        # context anchor 완화: 키워드 없어도 (a) "년생" marker (b) 풀네임 인접 OK
        has_marker = _has_birth_marker_after(text, m.end())
        has_name_ctx = _has_person_context_nearby(text, m.start(), m.end())
        if kw is None and not has_marker and not has_name_ctx:
            continue  # 단순 날짜 (회의·작성일 등) — 거부
        span = (m.start(), m.end())
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.HIGH,
            confidence=0.95,
            evidence=[
                "pattern:birth_korean",
                f"date:{year}-{month:02d}-{day:02d}",
                f"keyword:{kw}" if kw else "marker:생",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "year": year, "month": month, "day": day,
                "format": "korean", "category": CATEGORY,
            },
        )

    # 패턴 2: 숫자 구분자 (YYYY.M.D)
    for m in _PATTERN_NUMERIC.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        year = _normalize_year(int(m.group(1)))
        if year is None:
            continue
        month, day = int(m.group(3)), int(m.group(4))
        if not _valid_date(year, month, day):
            continue
        # 명시적 비-생일 키워드 직전 → 거부
        if _has_non_birth_keyword_before(text, m.start()):
            continue
        kw = _has_keyword_before(text, m.start())
        # 숫자 날짜: 키워드 또는 풀네임 인접 필요
        if kw is None and not _has_person_context_nearby(text, m.start(), m.end()):
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.HIGH,
            confidence=0.9,
            evidence=[
                "pattern:birth_numeric",
                f"date:{year}-{month:02d}-{day:02d}",
                f"keyword:{kw}",
            ],
            legal_basis=LEGAL_BASIS,
            extra={
                "year": year, "month": month, "day": day,
                "format": "numeric", "category": CATEGORY,
            },
        )

    # 패턴 3: YY년생 (연도만, "생" marker 자체가 anchor)
    for m in _PATTERN_BIRTH_YEAR.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        year = _normalize_year(int(m.group(1)))
        if year is None:
            continue
        seen.add(span)
        yield DetectionResult(
            label=LABEL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.85,
            evidence=["pattern:birth_year_only", f"year:{year}", "marker:년생"],
            legal_basis=LEGAL_BASIS,
            extra={
                "year": year, "format": "year_only", "category": CATEGORY,
            },
        )
