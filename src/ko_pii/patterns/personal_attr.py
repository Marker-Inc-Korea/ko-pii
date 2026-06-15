"""인적 속성 (Personal Attributes) — 학력·전공·직책·측정치.

검출 카테고리:
- ``EDUCATION`` (OGG_EDUCATION) : 대학교/전문대 (사전 매칭)
- ``MAJOR``     (FD_MAJOR)      : 전공·학과 (사전 + suffix 정규화)
- ``POSITION``  (CV_POSITION)   : 직책·직급 (titles 사전, 단독 emit)
- ``AGE``       (QT_AGE)         : 32세 / 32살
- ``HEIGHT``    (QT_LENGTH)      : 175cm / 1.75m
- ``WEIGHT``    (QT_WEIGHT)      : 70kg / 70kilo

위험도 정책:
- EDUCATION, MAJOR: MEDIUM/LOW (quasi-identifier)
- POSITION: LOW (단독은 직책일 뿐)
- AGE/HEIGHT/WEIGHT: INFO (단독 PII 아님, 결합위험도 산정용)

Legal basis: 개인정보보호법 제2조; 「개인정보 비식별 조치 가이드라인」
준식별자 (Quasi-Identifier) 분류 — 다른 정보와 결합 시 재식별 위험.
"""
from __future__ import annotations

import re
from typing import Iterator

from ko_pii.core.types import DetectionResult, RiskLevel

LEGAL_BASIS = "개인정보보호법 제2조"


# ═══════════════════════════════════════════════════════════════════════
# EDUCATION (학력)
# ═══════════════════════════════════════════════════════════════════════
# 대학교 정식명: 2-15자 + (대학교/대학/대학원/전문대학/대학원대학교)
# 약칭: 2-5자 + 대 (서울대/연대/고대 등) — 사전 매칭 필수
# 외국어 약칭: KAIST/POSTECH/UNIST/GIST/DGIST
# 초중고: 2-10자 + (초/중/고/초등학교/중학교/고등학교)
# 학교 검출 — alternation 별 named group, non-capturing outer
_EDUCATION_PATTERN = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"(?:"
    r"(?P<full>[가-힣]{2,15}(?:대학교|대학원대학교|전문대학|대학원|대학))|"
    r"(?P<abbrev>[가-힣]{1,5}대)|"  # 1자 prefix 허용 — "고대/홍대/이대/연대"
    r"(?P<eng>KAIST|POSTECH|UNIST|GIST|DGIST)|"
    r"(?P<kor>카이스트|포스텍|유니스트|지스트|디지스트)|"
    r"(?P<elem>[가-힣]{2,10}초등학교|[가-힣]{2,8}초)|"
    r"(?P<mid>[가-힣]{2,10}중학교|[가-힣]{2,8}중)|"
    r"(?P<high>[가-힣]{2,10}고등학교|[가-힣]{2,8}고)"
    r")"
    r"(?![가-힣A-Za-z])"
)


_SCHOOL_ANCHORS = (
    "졸업", "다녀", "다닌", "출신", "재학", "입학", "퇴학", "전학",
    "모교", "동문", "동창",
)


def _has_school_anchor(text: str, start: int, end: int, window: int = 15) -> bool:
    head = text[max(0, start - window): start]
    tail = text[end: end + window]
    return any(kw in head or kw in tail for kw in _SCHOOL_ANCHORS)


def detect_education(text: str) -> Iterator[DetectionResult]:
    from ko_pii.dictionaries.universities import (
        is_university, normalize_university,
    )
    for m in _EDUCATION_PATTERN.finditer(text):
        raw = m.group(0)
        # 약칭이면 사전 검증
        if m.group("abbrev"):
            if not is_university(raw):
                continue
            canonical = normalize_university(raw)
            edu_type = "university_abbrev"
        elif m.group("full") or m.group("eng") or m.group("kor"):
            if not is_university(raw):
                continue
            canonical = normalize_university(raw)
            edu_type = "university"
        elif m.group("elem"):
            # 정식명 (X초등학교) 은 anchor 없이도 OK, 약칭 (X초) 은 anchor 필수
            canonical = raw
            edu_type = "elementary_school"
            if raw.endswith("초") and not raw.endswith("초등학교"):
                if not _has_school_anchor(text, m.start(), m.end()):
                    continue
        elif m.group("mid"):
            canonical = raw
            edu_type = "middle_school"
            if raw.endswith("중") and not raw.endswith("중학교"):
                if not _has_school_anchor(text, m.start(), m.end()):
                    continue
        elif m.group("high"):
            canonical = raw
            edu_type = "high_school"
            if raw.endswith("고") and not raw.endswith("고등학교"):
                if not _has_school_anchor(text, m.start(), m.end()):
                    continue
        else:
            continue
        yield DetectionResult(
            label="EDUCATION",
            text=raw,
            start=m.start(),
            end=m.end(),
            risk_level=RiskLevel.MEDIUM,
            confidence=0.95 if edu_type.startswith("university") else 0.85,
            evidence=["pattern:education", f"type:{edu_type}", f"canonical:{canonical}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "canonical": canonical, "type": edu_type},
        )


# ═══════════════════════════════════════════════════════════════════════
# MAJOR (전공)
# ═══════════════════════════════════════════════════════════════════════
# 명확한 학과/학부/전공 suffix — lookahead 없음 (조사 부착 "경영학과니까" 매칭).
_MAJOR_PATTERN_LONG = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"([가-힣]{1,11}(?:학과|학부|전공))"
)

# 짧은 학/과 suffix — 합성어 거부 위해 lookahead 유지 ("법학", "의예과").
_MAJOR_PATTERN_SHORT = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"([가-힣]{1,10}(?:학|과))"
    r"(?![가-힣A-Za-z])"
)

# 단과대 약칭 — 의대/공대/미대/약대/법대/치대/한의대 등 (KDPII gold 빈출)
_MAJOR_FACULTY_ABBREV: frozenset[str] = frozenset([
    "의대", "치대", "한의대", "약대", "수의대", "의과대학",
    "법대", "행정대", "경상대학", "경상대",
    "공대", "미대", "음대", "체대", "예대", "사범대",
    "신학대", "농대", "건축대",
    "경영대", "생과대",  # KDPII gold 보강
])
_MAJOR_FACULTY_PATTERN = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"([가-힣]{2,4})"
    r"(?![가-힣A-Za-z])"
)


def detect_major(text: str) -> Iterator[DetectionResult]:
    from ko_pii.dictionaries.majors import is_major, normalize_major
    seen: set[tuple[int, int]] = set()
    # 1) 학과/학부/전공 suffix (lookahead 없음 — 조사 부착도 매칭)
    for m in _MAJOR_PATTERN_LONG.finditer(text):
        raw = m.group(1)
        if not is_major(raw):
            continue
        span = (m.start(1), m.end(1))
        if span in seen:
            continue
        seen.add(span)
        canonical = normalize_major(raw)
        yield DetectionResult(
            label="MAJOR",
            text=raw,
            start=span[0],
            end=span[1],
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            evidence=["pattern:major", f"canonical:{canonical}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "canonical": canonical},
        )
    # 2) 짧은 학/과 suffix — "법학", "의예과", "수학" 등
    for m in _MAJOR_PATTERN_SHORT.finditer(text):
        raw = m.group(1)
        if not is_major(raw):
            continue
        span = (m.start(1), m.end(1))
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        seen.add(span)
        canonical = normalize_major(raw)
        yield DetectionResult(
            label="MAJOR",
            text=raw,
            start=span[0],
            end=span[1],
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            evidence=["pattern:major_short", f"canonical:{canonical}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "canonical": canonical},
        )
    # 3) 단과대 약칭 — 의대/공대/미대/약대/법대 등 (KDPII gold MAJOR 로 라벨)
    for m in _MAJOR_FACULTY_PATTERN.finditer(text):
        raw = m.group(1)
        if raw not in _MAJOR_FACULTY_ABBREV:
            continue
        span = (m.start(1), m.end(1))
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        seen.add(span)
        yield DetectionResult(
            label="MAJOR",
            text=raw,
            start=span[0],
            end=span[1],
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            evidence=["pattern:major_faculty_abbrev"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "canonical": raw, "kind": "faculty_abbrev"},
        )


# ═══════════════════════════════════════════════════════════════════════
# POSITION (직책)
# ═══════════════════════════════════════════════════════════════════════
# titles 사전을 사용 — 단독 직책 emit (PERSON 컨텍스트와 별개)
# *키워드 anchor 필수* — "직급:" "직책:" "직위:" 등이 5자 이내 앞에 있어야
# 단독 emit. 이게 없으면 PERSON 검출에서 직책 인접 단서로만 사용됨.
_POSITION_ANCHORS = ("직급", "직책", "직위", "보직", "직군")
_POSITION_PATTERN = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"([가-힣]{1,6})"
    r"(?![가-힣A-Za-z])"
)


def _position_anchor_before(text: str, start: int, window: int = 12) -> str | None:
    head = text[max(0, start - window): start]
    for kw in _POSITION_ANCHORS:
        if kw in head:
            return kw
    return None


_POSITION_HONORIFIC_PATTERN = re.compile(
    r"(?<![가-힣A-Za-z])"
    r"([가-힣]{1,6})님"
    # lookahead 제거 — "부장님께/부장님이/팀장님일" 같은 조사 부착 허용
)


def detect_position(text: str) -> Iterator[DetectionResult]:
    from ko_pii.dictionaries.titles import is_title, title_domain
    seen: set[tuple[int, int]] = set()
    # 1) 키워드 anchor 모드 ("직급:/직책:/직위:")
    for m in _POSITION_PATTERN.finditer(text):
        raw = m.group(1)
        if not is_title(raw):
            continue
        kw = _position_anchor_before(text, m.start(1))
        if kw is None:
            continue
        span = (m.start(1), m.end(1))
        if span in seen:
            continue
        seen.add(span)
        domain = title_domain(raw) or "unknown"
        yield DetectionResult(
            label="POSITION",
            text=raw,
            start=span[0],
            end=span[1],
            risk_level=RiskLevel.LOW,
            confidence=0.85,
            evidence=["pattern:position", f"keyword:{kw}", f"domain:{domain}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "domain": domain},
        )

    # 2) 호칭 모드 — "부장님", "사장님", "팀장님" 같이 "님" suffix 가 붙은 직급
    #    KDPII 대화체에서 빈번 ("아 저 재무팀 김명진 과장님 만나러 왔는데요")
    for m in _POSITION_HONORIFIC_PATTERN.finditer(text):
        raw = m.group(1)
        if not is_title(raw):
            continue
        span = (m.start(1), m.end(1))
        # 호칭 자체 ("부장님") 보다는 직급 부분만 ("부장") emit
        if any(span[0] < e and s < span[1] for s, e in seen):
            continue
        seen.add(span)
        domain = title_domain(raw) or "unknown"
        yield DetectionResult(
            label="POSITION",
            text=raw,
            start=span[0],
            end=span[1],
            risk_level=RiskLevel.LOW,
            confidence=0.8,
            evidence=["pattern:position_honorific", f"domain:{domain}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "domain": domain, "honorific": True},
        )



# ═══════════════════════════════════════════════════════════════════════
# AGE / HEIGHT / WEIGHT (측정치)
# ═══════════════════════════════════════════════════════════════════════
# "32세/30살" — 조사·연결어미 다양 ("30살인데/30살밖에")
# 한글 lookahead 제거 — KDPII gold 와 substring overlap 최대화.
# "X세기/세대" 같은 단위 매칭은 INFO 수준이라 가독성 손해 없음.
_AGE_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{1,3})"
    r"\s*(?:세|살)"
    r"(?![0-9])"   # 숫자 직후만 거부 (다른 측정치와 충돌 방지)
)

# 연령대 — "30대/20대 후반/40대 초반" 등 ("X0대" 형식, 10~99)
_AGE_RANGE_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{1,2}0)대"
    r"(?![0-9가-힣])"
)

# 한글 음역 — "서른두 살", "스물여섯 살", "마흔 다섯 살" 등
_KOREAN_AGE_TENS = {
    "열": 10, "스물": 20, "서른": 30, "마흔": 40, "쉰": 50,
    "예순": 60, "일흔": 70, "여든": 80, "아흔": 90,
}
_KOREAN_AGE_ONES = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5,
    "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9,
}
_KOREAN_AGE_TWENTIES = {
    "스무": 20,
}
_KOREAN_AGE_PATTERN = re.compile(
    r"(?<![가-힣])"
    r"(스무|"
    r"(?:열|스물|서른|마흔|쉰|예순|일흔|여든|아흔)(?:\s*(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉))?|"
    r"한|두|세|네|다섯|여섯|일곱|여덟|아홉)"  # 일의자리 단독 ("한 살/세 살")
    r"\s*살"
)

# 한자어 나이 명사 — 환갑/칠순/팔순 등 (60대 이상 명시적 호칭)
_KOREAN_AGE_NOUN = {
    "환갑": 60, "회갑": 60, "진갑": 61,
    "고희": 70, "칠순": 70, "고희연": 70,
    "산수": 80, "팔순": 80,
    "구순": 90, "졸수": 90,
    "백수": 99, "백세": 100,
}
_KOREAN_AGE_NOUN_PATTERN = re.compile(
    r"(?<![가-힣])"
    r"(환갑|회갑|진갑|고희연|고희|칠순|산수|팔순|구순|졸수|백수|백세)"
    r"(?![가-힣])"
)

# 영유아 연령 — N개월 + 키워드 anchor ("아기/돌/생후/만") 필요
_INFANT_MONTH_PATTERN = re.compile(
    r"(?<![0-9])"
    r"(\d{1,2})\s*개월"
    r"(?![0-9])"
)
_INFANT_ANCHORS = ("아기", "아이", "딸", "아들", "둘째", "첫째",
                   "생후", "만 ", "되었", "되었어", "되었네", "지났",
                   "돌", "출산")

_HEIGHT_PATTERN = re.compile(
    r"(?<![0-9.])"
    r"(\d{2,3}(?:\.\d{1,2})?)"
    r"\s*(?:cm|센티(?:미터)?|㎝)"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)

# 키 (m 단위): 1.75m / 1m75 — 위험은 일반 거리와 충돌
_HEIGHT_M_PATTERN = re.compile(
    r"(?<![0-9.])"
    r"(1\.\d{1,2})\s*m"
    r"(?![A-Za-z])"
)

_WEIGHT_PATTERN = re.compile(
    r"(?<![0-9.])"
    r"(\d{1,3}(?:\.\d{1,2})?)"
    r"\s*(?:kg|키로(?:그램)?|킬로(?:그램)?|㎏|kilogram)"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)


def _parse_korean_age(token: str) -> int | None:
    """'서른두', '스물여섯', '마흔다섯' 등을 숫자로 변환.

    일의자리 단독 ("한/두/세/.../아홉") 도 지원 — "한 살" 같은 영유아 표현.
    """
    if token in _KOREAN_AGE_TWENTIES:
        return _KOREAN_AGE_TWENTIES[token]
    # 일의자리 단독
    if token in _KOREAN_AGE_ONES:
        return _KOREAN_AGE_ONES[token]
    # 십대 + (일의자리)
    for tens_kor, tens_val in _KOREAN_AGE_TENS.items():
        if token.startswith(tens_kor):
            rest = token[len(tens_kor):].strip()
            if not rest:
                return tens_val
            if rest in _KOREAN_AGE_ONES:
                return tens_val + _KOREAN_AGE_ONES[rest]
    return None


def detect_measurements(text: str) -> Iterator[DetectionResult]:
    seen_age: set[tuple[int, int]] = set()
    for m in _AGE_PATTERN.finditer(text):
        age = int(m.group(1))
        if 0 <= age <= 150:
            span = (m.start(), m.end())
            seen_age.add(span)
            yield DetectionResult(
                label="AGE", text=m.group(0),
                start=span[0], end=span[1],
                risk_level=RiskLevel.INFO, confidence=0.95,
                evidence=["pattern:age", f"value:{age}"],
                legal_basis=LEGAL_BASIS,
                extra={"category": "준식별자", "value": age, "unit": "year"},
            )

    # 연령대 ("30대/40대 후반")
    for m in _AGE_RANGE_PATTERN.finditer(text):
        age = int(m.group(1))
        if 10 <= age <= 90:
            span = (m.start(), m.end())
            if any(span[0] < e and s < span[1] for s, e in seen_age):
                continue
            seen_age.add(span)
            yield DetectionResult(
                label="AGE", text=m.group(0),
                start=span[0], end=span[1],
                risk_level=RiskLevel.INFO, confidence=0.85,
                evidence=["pattern:age_range", f"value:{age}대"],
                legal_basis=LEGAL_BASIS,
                extra={"category": "준식별자", "value": age, "unit": "decade",
                       "format": "range"},
            )

    # 한글 음역
    for m in _KOREAN_AGE_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen_age):
            continue
        token = m.group(1).strip()
        parsed = _parse_korean_age(token)
        if parsed is None or not (0 <= parsed <= 99):
            continue
        age = parsed
        seen_age.add(span)
        yield DetectionResult(
            label="AGE", text=m.group(0),
            start=span[0], end=span[1],
            risk_level=RiskLevel.INFO, confidence=0.85,
            evidence=["pattern:age_korean", f"value:{age}", f"token:{token}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "value": age, "unit": "year",
                   "format": "korean"},
        )

    # 한자어 나이 명사 (환갑/칠순/팔순 등)
    for m in _KOREAN_AGE_NOUN_PATTERN.finditer(text):
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen_age):
            continue
        token = m.group(1)
        age = _KOREAN_AGE_NOUN[token]
        seen_age.add(span)
        yield DetectionResult(
            label="AGE", text=m.group(0),
            start=span[0], end=span[1],
            risk_level=RiskLevel.INFO, confidence=0.9,
            evidence=["pattern:age_noun", f"value:{age}", f"token:{token}"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "value": age, "unit": "year",
                   "format": "noun"},
        )

    # 영유아 연령 — N개월 + anchor 필요 (일반 N개월 차이/일정/근무 등 거부)
    for m in _INFANT_MONTH_PATTERN.finditer(text):
        months = int(m.group(1))
        if not (0 <= months <= 60):  # 5세 이하만
            continue
        span = (m.start(), m.end())
        if any(span[0] < e and s < span[1] for s, e in seen_age):
            continue
        # anchor 윈도우 25자
        window_start = max(0, span[0] - 25)
        window_end = min(len(text), span[1] + 10)
        if not any(a in text[window_start:window_end] for a in _INFANT_ANCHORS):
            continue
        seen_age.add(span)
        yield DetectionResult(
            label="AGE", text=m.group(0),
            start=span[0], end=span[1],
            risk_level=RiskLevel.INFO, confidence=0.85,
            evidence=["pattern:age_months", f"value:{months}개월"],
            legal_basis=LEGAL_BASIS,
            extra={"category": "준식별자", "value": months, "unit": "month",
                   "format": "infant"},
        )

    for m in _HEIGHT_PATTERN.finditer(text):
        height = float(m.group(1))
        if 50 <= height <= 250:
            yield DetectionResult(
                label="HEIGHT", text=m.group(0),
                start=m.start(), end=m.end(),
                risk_level=RiskLevel.INFO, confidence=0.9,
                evidence=["pattern:height", f"value:{height}cm"],
                legal_basis=LEGAL_BASIS,
                extra={"category": "준식별자", "value": height, "unit": "cm"},
            )

    for m in _HEIGHT_M_PATTERN.finditer(text):
        height_m = float(m.group(1))
        if 0.5 <= height_m <= 2.5:
            yield DetectionResult(
                label="HEIGHT", text=m.group(0),
                start=m.start(), end=m.end(),
                risk_level=RiskLevel.INFO, confidence=0.85,
                evidence=["pattern:height_m", f"value:{height_m}m"],
                legal_basis=LEGAL_BASIS,
                extra={"category": "준식별자", "value": height_m * 100, "unit": "cm"},
            )

    for m in _WEIGHT_PATTERN.finditer(text):
        weight = float(m.group(1))
        if 1 <= weight <= 300:
            yield DetectionResult(
                label="WEIGHT", text=m.group(0),
                start=m.start(), end=m.end(),
                risk_level=RiskLevel.INFO, confidence=0.9,
                evidence=["pattern:weight", f"value:{weight}kg"],
                legal_basis=LEGAL_BASIS,
                extra={"category": "준식별자", "value": weight, "unit": "kg"},
            )


# ═══════════════════════════════════════════════════════════════════════
# 통합 detect 진입점
# ═══════════════════════════════════════════════════════════════════════
def detect(text: str) -> Iterator[DetectionResult]:
    """모든 인적 속성 카테고리 검출."""
    yield from detect_education(text)
    yield from detect_major(text)
    yield from detect_position(text)
    yield from detect_measurements(text)
