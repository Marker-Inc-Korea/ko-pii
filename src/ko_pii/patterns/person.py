"""성명 (Korean person name) 컨텍스트 기반 검출 — Phase 3.

전체 파이프라인:
  1. 결정적 PII (RRN/PHONE/EMAIL/MEDICAL_INSURANCE) 위치를 별도 패스에서
     식별해 두고, 그 근방을 "deterministic_nearby" 플래그로 표시.
  2. 후보 추출: 2~4글자 한글 토큰 + 성씨 시작.
  3. 컨텍스트 점수 (`context.context_rules.score_candidate`) 로 평가.
  4. 임계값 이상이면 emit + 누적 사전 등록.
  5. 누적 사전 보유 이름은 약한 단서로 등장해도 두 번째 패스에서 emit.

Legal basis: 개인정보보호법 제2조 (성명을 통한 개인 식별).
"""
from __future__ import annotations

import re
from typing import Iterable, Iterator

from ko_pii.context.context_rules import NameCandidate, score_candidate
from ko_pii.context.name_dictionary import NameDictionary
from ko_pii.context.name_origin import classify_name_origin
from ko_pii.context.name_syllables import name_shape_bonus
from ko_pii.context.particles import strip_trailing_particle
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.dictionaries.agencies import is_agency
from ko_pii.dictionaries.agency_abbrev import normalize_agency
from ko_pii.dictionaries.agency_titles import is_valid_agency_title
from ko_pii.dictionaries.common_words import is_common_word
from ko_pii.dictionaries.districts import (
    is_country, is_common_dong, is_district, is_extra_city, is_province,
)
from ko_pii.dictionaries.field_labels import is_field_label
from ko_pii.dictionaries.universities import is_university
from ko_pii.dictionaries.surnames import surname_prefix_len
from ko_pii.dictionaries.titles import is_title

LABEL = "PERSON"
LEGAL_BASIS = "개인정보보호법 제2조"
CATEGORY = "일반개인정보"

# 이름 후보: 한글 2~4글자 (조사 포함하면 더 길어질 수 있음)
_CANDIDATE = re.compile(r"(?<![가-힣])([가-힣]{2,6})(?![가-힣])")

# 결정적 PII 의 *위치 마커* 만 빠르게 찾기 위한 보조 패턴 (성능)
# 주: 길이 상한({1,64}/{1,255})과 lookaround 경계는 ReDoS/quadratic 방지용 — 이메일
# local-part 의 무제한 `+` 는 긴 영숫자열에서 매 시작 위치마다 백트래킹해 O(n²)가 된다
# (RFC 5321 제한이라 recall 손실 없음). RRN 도 \b 대신 digit lookaround 로 경계를 둔다.
_DETERMINISTIC_HINTS = re.compile(
    r"(?<![0-9])\d{6}-?\d{7}(?![0-9])"            # RRN/FRN
    r"|01[01679][-\.\s]?\d{3,4}[-\.\s]?\d{4}"     # mobile
    r"|[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}"  # email
)

# 한국어 동사/형용사·계사(이다) 활용형. 이름은 거의 이 형태로 끝나지 않음.
_VERB_LIKE_SUFFIXES = (
    # 하다 활용
    "하다", "하고", "하여", "하지", "하니", "하면", "한다", "한", "할", "함",
    "하기", "하는", "하신", "하시", "하셨", "하셔", "하게", "하며", "하면서",
    "했다", "했고", "했지", "했음", "했으며",
    # 되다 활용
    "되다", "되고", "되어", "되지", "되니", "되면", "된다", "된", "될", "됨",
    "되기", "되는", "되며", "되었",
    # 드리다 활용
    "드린", "드리는", "드리고", "드립니다", "드린다", "드리며",
    # 이다 계사 + 명사화 (단계임/사실임/현실임 등)
    "임", "임을", "임에", "임으로", "임에도", "임이",
    "인", "인지", "인데", "인가", "이라",
    # 형용사 관형형 / 활용형 (강한·이상한·민감한 등 — surname-시작 2~3자 빈출)
    "운", "운데", "운지",         # 즐거운·괜찮은
    "라운", "로운", "스러운",      # 사랑스러운·풍요로운
    "이다", "이며", "이지만", "이라서",
    # 부사형
    "히",                         # 분명히·정확히 (단, 명사 부분 보존)
    # 어미 자주 끝
    "에서", "에는", "에도", "에게",
)


# 부분 가명 (이미 가명화된 표기) — PII 가 아니므로 거부
# "박씨", "정모", "이씨", "김군", "박양", "강씨" 등
_ANONYMIZED_MARKERS: frozenset[str] = frozenset({
    "씨", "모", "군", "양",
})


def _looks_like_anonymized(raw: str) -> bool:
    """길이 2자 + 끝 글자가 가명 마커 → 이미 익명화된 표기."""
    return len(raw) == 2 and raw[-1] in _ANONYMIZED_MARKERS


# 한국어 명사 접미사 / 복수 표지 — 사람 이름에는 거의 안 등장
# - 들 (복수: 사람들·배우들·국민들·우리들)
# - 성 (성격·가능성·정확성·매력·생산성)
# - 력 (연기력·실력·매력·동력·체력) — 단, "력" 단독 글자가 일부 이름에 있음
# - 감 (정의감·만족감·소외감·책임감·기대감)
# - 률 (성공률·시청률·확률)
# - 도 (정확도·만족도) — 단, 행정 단위 "도" 와 충돌 — admin_unit 에서 이미 처리
# - 적 (긍정적·일반적·전반적) — 형용사 접미사
_NOUN_SUFFIXES_FORBIDDEN: tuple[str, ...] = (
    "들", "성", "력", "감", "률", "적",
    # 안전 확장 (이름 끝 글자 절대 충돌 없는 것만)
    "증", "점", "팀", "부", "처", "회", "료", "님", "측", "쪽",
)


def _looks_like_common_noun_suffix(raw: str) -> bool:
    """3자+ 토큰 끝이 일반 명사 접미사면 True (예: 사람들·연기력·매력·기대감)."""
    return len(raw) >= 3 and any(raw.endswith(s) for s in _NOUN_SUFFIXES_FORBIDDEN)


# 토큰 마지막 글자가 *명확한 동사 활용 어미* 면 거부.
# 이름 끝 글자 충돌 회피로 conservative — "지", "사", "세", "아", "어", "야",
# "라", "고", "해", "도", "더", "든" 등은 이름에 흔하므로 제외.
_VERB_ENDINGS_FINAL: frozenset[str] = frozenset("다네요까잖면려")

# 토큰 마지막 글자가 *명확한 조사 부착* 형태이면 거부.
# "도/만/뿐" 등은 이름 끝 글자 충돌 가능 → 제외.
_PARTICLE_FINAL: frozenset[str] = frozenset("은는이가을를의에로와과")

# 한국어 *어말 연결어미 + 종결 어미* 패턴 — 2자 이상 suffix.
# 이런 어말이 토큰 끝에 붙으면 일반 어휘이지 인명 아님 (예: "같은데/먹는데/하다가").
# KDPII PERSON FP 분석 기반.
_COMMON_KOREAN_ENDINGS: tuple[str, ...] = (
    # 연결어미
    "은데", "는데", "라서", "어서", "아서", "면서", "다가",
    "지만", "거나", "더라", "더라도", "이라도",
    "고요", "는걸", "는군", "더군", "는데요", "거든",
    "을까", "을지", "려고", "려면", "도록", "토록",
    # 종결어미 (반말·존댓말 변형)
    "이에요", "예요", "이고", "이며", "이니", "이라",
    "입니다", "이지요",
    # 조사 결합
    "에서", "에게", "한테", "보다", "처럼", "마다", "조차", "마저", "부터", "까지",
    "라고", "이라고",
)


def _ends_with_common_korean_ending(raw: str) -> bool:
    """토큰이 흔한 한국어 어말로 끝나면 True (PERSON 거부 신호)."""
    return any(raw.endswith(end) for end in _COMMON_KOREAN_ENDINGS)


def _ends_with_verb_or_particle(raw: str) -> bool:
    """토큰 끝이 동사 활용 또는 조사 부착이면 True (PERSON 거부 신호)."""
    if not raw:
        return False
    return raw[-1] in _VERB_ENDINGS_FINAL or raw[-1] in _PARTICLE_FINAL


# 한국어 동사 어간 빈출 패턴 — "다" 없이 종결되어 candidate 가 매칭되는 형태
# 예: "나오", "만드", "추정되", "재미있", "흘러내리"
# 끝이 *어간 + 종결* 패턴 (오/되/있/지/리/하/가/와/와) 인 3자+ 토큰 페널티
_VERB_STEM_FINAL_PATTERNS: tuple[str, ...] = (
    "추정되", "재미있", "재밌",
    "나오", "들어가", "들어와",
    "만드", "만들", "만나", "흐르",
)


def _looks_like_verb_stem(raw: str) -> bool:
    return any(raw.endswith(p) for p in _VERB_STEM_FINAL_PATTERNS)


# 토큰 안에 직책이 *포함* 된 경우 — 예: "강회장이", "김의원이", "박교수가"
# stem 끝 부분이 직책이면 직책 부분 떼고 앞부분만 PERSON 후보로 처리.
_EMBEDDED_TITLE_SUFFIXES: tuple[str, ...] = (
    "회장", "사장", "이사", "대표", "대표이사", "부사장", "전무", "상무",
    "본부장", "팀장", "실장", "센터장", "원장", "지점장",
    # 회사 직급 (성씨 1자 + 직급 = 호칭, PII 아님 — "김부장" "박과장" 등)
    "부장", "과장", "차장", "주임", "대리", "사원",
    "수석", "선임", "책임", "전임",
    "의원", "장관", "차관", "총리", "비서관", "보좌관",
    "교수", "박사", "강사",
    "의사", "약사", "간호사", "한의사",
    "변호사", "검사", "판사", "법무사",
    "대사", "총영사", "영사",
    "선수", "감독", "코치",
    "기자", "PD", "작가",
)


def _split_embedded_title(stem: str) -> tuple[str, str | None]:
    """``"강회장"`` → ``("강", "회장")``. 분리 안 되면 ``(stem, None)``.

    조건: stem 끝이 직책으로 끝나야 하고, 앞부분이 1~3자 한글이어야 한다.
    """
    for suf in sorted(_EMBEDDED_TITLE_SUFFIXES, key=len, reverse=True):
        if stem.endswith(suf) and len(stem) > len(suf):
            front = stem[: -len(suf)]
            if 1 <= len(front) <= 3 and all("가" <= c <= "힣" for c in front):
                return front, suf
    return stem, None


# 이름 끝 음절 자주 등장 패턴 — recall 보강용 보너스 (강한 신호 아님)
_NAME_FINAL_SYLLABLES: frozenset[str] = frozenset({
    # 남자 이름 빈출
    "수", "호", "준", "훈", "진", "민", "철", "혁", "한", "현",
    "성", "석", "환", "식", "원", "운", "웅", "용", "영", "정",
    "재", "재", "균", "근", "광", "관", "구", "규", "기", "길",
    "동", "두", "찬", "철", "충", "탁", "태", "택", "필", "필",
    # 여자 이름 빈출
    "지", "희", "은", "정", "영", "미", "현", "주", "경", "선",
    "연", "린", "린", "옥", "원", "유", "윤", "이", "인", "임",
    "자", "전", "정", "조", "주", "지", "지", "진", "참", "채",
    "혜", "화", "효", "후", "흠", "흥",
    # 중성
    "아", "야", "예", "오", "우", "원", "유", "은", "이",
})


def _has_name_like_final(stem: str) -> bool:
    """이름 끝 글자가 *흔한 이름 글자* 면 True (약한 신호)."""
    return len(stem) >= 2 and stem[-1] in _NAME_FINAL_SYLLABLES


# 나이·성별·신원 단서 — 이름 인접 시 PERSON 확신 ↑
# "홍길동(32세)", "홍길동 32세", "홍길동, 남자", "홍길동(남)"
# "남"/"여" 단독은 동사·일반어 (남기다/여기다) 충돌 우려 → 괄호 안일 때만 허용
_AGE_GENDER_PATTERN = re.compile(
    r"\s*\(\s*(?:\d{1,3}\s*세|남자|여자|남|여|미혼|기혼)\s*\)"
    r"|\s*,\s*(?:\d{1,3}\s*세|남자|여자|미혼|기혼)"
    r"|\s+\d{1,3}\s*세\b"
)


# 3중 매크로 패턴 — <AGENCY> <PERSON> <TITLE>
# 예: "기획재정부 김민수 장관", "환경부 박영수 차관", "경찰청 이형사 경감"
# 정규식이 *세 토큰* 을 한 번에 매칭. 매칭되면 *극강* PERSON 확신.
_MACRO_AGENCY_PERSON_TITLE = re.compile(
    r"(?<![가-힣A-Za-z0-9])"
    r"([가-힣]{2,15}(?:부|처|청|위원회|원|국|실|단|장|소))"   # <AGENCY>
    r"(?:\s+|[\s\-/])"
    r"([가-힣]{2,4})"                                          # <PERSON 후보>
    r"(?:\s+|[\s\-/])"
    r"([가-힣]{2,8})"                                          # <TITLE 후보>
    r"(?![가-힣A-Za-z0-9])"
)


def _macro_matches(text: str) -> Iterator[tuple[int, int, str, str, str]]:
    """매크로 패턴 매칭 → ``(person_start, person_end, agency, person, title)``.

    조건: agency 가 *알려진 기관* (또는 약칭) 이고, title 이 *해당 기관에서
    유효* 한 직급/직위.
    """
    for m in _MACRO_AGENCY_PERSON_TITLE.finditer(text):
        agency = m.group(1)
        person_cand = m.group(2)
        title_cand = m.group(3)
        # agency 검증 — 사전 + 약칭
        canonical_agency = None
        if is_agency(agency):
            canonical_agency = agency
        else:
            normalized = normalize_agency(agency)
            if normalized:
                canonical_agency = normalized
        if canonical_agency is None:
            continue
        # title 검증 — 해당 기관에서 유효한가?
        if not is_valid_agency_title(canonical_agency, title_cand):
            continue
        # person 후보 위치 — group(2) 시작
        person_start = m.start(2)
        person_end = m.end(2)
        yield person_start, person_end, canonical_agency, person_cand, title_cand


def _has_age_or_gender_after(text: str, end: int, window: int = 12) -> str | None:
    tail = text[end: end + window]
    m = _AGE_GENDER_PATTERN.match(tail)
    if m:
        return m.group(0).strip()
    return None


def _looks_like_verb_form(token: str) -> bool:
    """Heuristic: True if ``token`` ends with a common Korean verb/adj ending."""
    return any(token.endswith(s) for s in _VERB_LIKE_SUFFIXES)


# 행정구역 접미사. "경기도", "성남시", "가평군" 등이 surname-starting 2~3자
# 토큰으로 보이지만 사람 이름은 거의 이 형태로 끝나지 않는다. 단, 명시적
# field-label-before 가 있으면 override (드물게라도 가능성을 보존).
_ADMIN_UNIT_CHARS: frozenset[str] = frozenset(
    {"시", "군", "구", "도", "읍", "면", "리"}
)
_STREET_SUFFIXES: tuple[str, ...] = ("대로", "로", "길")


def _looks_like_admin_unit(raw: str) -> bool:
    return len(raw) >= 2 and raw[-1] in _ADMIN_UNIT_CHARS


def _looks_like_street_name(raw: str) -> bool:
    return len(raw) >= 3 and any(raw.endswith(s) for s in _STREET_SUFFIXES)


def detect(text: str) -> Iterator[DetectionResult]:
    """Yield PERSON detections.

    Two-pass strategy:
      Pass A: extract candidates, score them, emit those above threshold,
              and register into a per-document NameDictionary.
      Pass B: rescan candidates that were below threshold; if the (stem) is
              now in the dictionary, emit with boosted confidence.
    """
    yield from _detect_with_dict(text, NameDictionary())


def _detect_with_dict(
    text: str, name_dict: NameDictionary
) -> Iterator[DetectionResult]:
    deterministic_spans = [
        (m.start(), m.end()) for m in _DETERMINISTIC_HINTS.finditer(text)
    ]
    threshold = 0.50
    # 문장별 '기관 포함 여부' 캐시 — 같은 문장의 후보들이 단어 순회를 반복하지 않도록
    # score_candidate 에 공유(이게 없으면 person 검출이 O(n²)).
    _agency_cache: dict[tuple[int, int], bool] = {}

    # ------ Pass 0: 3중 매크로 패턴 — <AGENCY> <PERSON> <TITLE>
    # 고신뢰 인명 추출 + 누적 사전에 *즉시 등록* → 같은 문서 내 다른 등장도
    # 누적 사전 부스트로 잡힘
    macro_spans: set[tuple[int, int]] = set()
    for p_start, p_end, agency, person_text, title in _macro_matches(text):
        # 합리성 추가 검증 — 이름 부분이 common_word 가 아닌지
        if is_common_word(person_text):
            continue
        # field_label / title 자체는 PERSON 이 아님
        if is_field_label(person_text) or is_title(person_text):
            continue
        if is_agency(person_text) or normalize_agency(person_text) is not None:
            continue
        cand = NameCandidate(name=person_text, start=p_start, end=p_end)
        evidence = [
            "pattern:macro_agency_person_title",
            f"pos:agency({agency})",
            f"pos:title_validated({title})",
        ]
        # 매크로 통과 = 0.95 신뢰
        name_dict.add(person_text, 0.95, (p_start, p_end), evidence)
        macro_spans.add((p_start, p_end))

    pending: list[tuple[NameCandidate, float, list[str], str | None]] = []
    emitted: list[tuple] = []  # (cand, particle, score, evidence)
    # 매크로로 잡은 것은 우선 emit
    for p_start, p_end, agency, person_text, title in _macro_matches(text):
        if is_common_word(person_text):
            continue
        if is_field_label(person_text) or is_title(person_text):
            continue
        if is_agency(person_text) or normalize_agency(person_text) is not None:
            continue
        cand = NameCandidate(name=person_text, start=p_start, end=p_end)
        evidence = [
            "pattern:macro_agency_person_title",
            f"pos:agency({agency})",
            f"pos:title_validated({title})",
        ]
        emitted.append((cand, None, 0.95, evidence))
    # ------ Pass A
    for m in _CANDIDATE.finditer(text):
        raw = m.group(1)
        # 매크로로 이미 잡힌 span 은 중복 emit 방지
        if (m.start(), m.start() + len(raw)) in macro_spans:
            continue
        label_before = _label_before(text, m.start())
        # Reject raw tokens that match an agency in the dictionary, or look
        # like an administrative-unit name (경기도, 성남시, 가평군) — unless
        # a person-field label is right before.
        if not label_before:
            # Reject any token that is a known agency (full or abbreviation),
            # district, province, or street/admin-unit by suffix shape.
            if (is_agency(raw)
                    or normalize_agency(raw) is not None
                    or is_province(raw) or is_district(raw)
                    or _looks_like_admin_unit(raw)
                    or _looks_like_street_name(raw)):
                continue
        # Try stripping a trailing particle to get the bare name
        stem, particle = strip_trailing_particle(raw)
        if len(stem) < 2 or len(stem) > 4:
            continue
        # 부분 가명 표기 (박씨/이모/김군) — 이미 익명화된 표기이므로 거부
        if _looks_like_anonymized(stem):
            continue
        if is_common_word(stem):
            continue
        # Skip tokens that are themselves dictionary words (field label,
        # title, agency) — those are infrastructure markers, not names.
        if is_field_label(stem) or is_title(stem) or is_agency(stem):
            continue
        # Skip 행정구역명·국가명 — LC_ADDRESS 영역이지 PERSON 아님
        # (동대문구·화곡동·수원시·한국 등이 부분 매칭으로 PERSON 잡히는 것 차단)
        if (is_province(stem) or is_district(stem) or is_country(stem)
                or is_common_dong(stem) or is_extra_city(stem)):
            continue
        # Skip 학교명 (정식명·약칭 모두 universities 사전 활용)
        # "연세대학교/연세대/서울대/숭실대" 등 — 사전 매칭 + 학교 suffix 거부.
        if is_university(stem):
            continue
        if stem.endswith(("대학교", "고등학교", "중학교", "초등학교")):
            continue
        # Skip 은행명 (...은행 끝나는 토큰)
        if stem.endswith("은행"):
            continue
        # Skip tokens that look like Korean verb/adjective conjugations.
        if _looks_like_verb_form(stem):
            continue
        # Skip 복수형 (X들) / 명사 접미사 (X성·X력·X감 등) — 사람 이름 아님
        if _looks_like_common_noun_suffix(stem):
            continue
        # Skip 동사 어간 패턴 (나오·추정되·재미있 등)
        if _looks_like_verb_stem(stem):
            continue
        # Skip 토큰 끝이 동사 어미/조사 부착 형태 (KDPII FP 분석)
        # 단, 2자 토큰은 surname+이름 패턴이 흔하므로 예외 (성씨 확실한 경우에만)
        if len(stem) >= 3 and _ends_with_verb_or_particle(stem):
            continue
        # Skip 토큰이 흔한 한국어 어말로 끝남 ("같은데/먹는데/하라서" 등)
        if len(stem) >= 3 and _ends_with_common_korean_ending(stem):
            continue

        # Embedded title — "강회장이" 같이 토큰 안에 직책이 들어있으면
        # 직책 부분 떼고 앞부분 (성+이름 후보) 만 사용
        embedded_title: str | None = None
        original_stem = stem
        front, title_suffix = _split_embedded_title(stem)
        if title_suffix and len(front) >= 2:
            stem = front
            embedded_title = title_suffix
        elif title_suffix and len(front) == 1:
            # 1자 + 직책 (예: "강회장") — 1자 단독은 신뢰도 너무 낮음 → 거부
            continue

        # Heuristic: skip tokens without any leading surname unless the
        # field label is right before (we'll let the scorer decide).
        sp = surname_prefix_len(stem)
        if sp == 0 and not label_before:
            continue

        cand_start = m.start()
        cand_end = m.start() + len(stem)
        cand = NameCandidate(name=stem, start=cand_start, end=cand_end)
        det_nearby = _is_within(deterministic_spans, cand_start, window=25)
        # 추가 신호: 토큰 안 직책, 이름끝 음절, 나이/성별 인접, 음절 통계
        extra_signals: list[str] = []
        extra_score = 0.0
        if embedded_title:
            extra_score += 0.35
            extra_signals.append(f"pos:embedded_title({embedded_title})")
        if _has_name_like_final(stem):
            extra_score += 0.10
            extra_signals.append("pos:name_final_syllable")
        # Method 1: 음절 통계 likelihood
        shape_bonus = name_shape_bonus(stem)
        if shape_bonus > 0:
            extra_score += shape_bonus
            extra_signals.append(f"pos:name_likelihood({shape_bonus:.2f})")
        # 원본 토큰 끝(particle 포함) 다음 위치에서 나이/성별 단서
        age_gender = _has_age_or_gender_after(text, m.end())
        if age_gender:
            extra_score += 0.30
            extra_signals.append(f"pos:age_gender_after({age_gender})")
        score = score_candidate(
            text, cand,
            deterministic_nearby=det_nearby,
            name_dictionary_boost=name_dict.boost_for(stem),
            agency_cache=_agency_cache,
        )
        # 추가 신호 합산
        total_value = min(1.0, score.value + extra_score)
        total_evidence = list(score.evidence) + extra_signals

        # 동적 threshold:
        # - 2자 토큰: 끝 글자가 *이름 글자가 아니면* 엄격 (+0.10)
        # - 3자+ 토큰: 기본 임계값
        # - field_label 가 직전에 있거나 직책이 명시되면 기본 임계값
        eff_threshold = threshold
        if (len(stem) == 2
                and not _has_name_like_final(stem)
                and not label_before
                and not embedded_title
                and "pos:field_label" not in " ".join(total_evidence)
                and "pos:title" not in " ".join(total_evidence)):
            eff_threshold = threshold + 0.10
            total_evidence.append("threshold:strict_short")

        if total_value >= eff_threshold:
            name_dict.add(
                stem, total_value, (cand_start, cand_end), total_evidence
            )
            emitted.append((cand, particle, total_value, total_evidence))
        else:
            pending.append((cand, total_value, total_evidence, particle))

    # ------ Method 2: 같은 문장 내 후보 상호 보강 (Co-occurrence Boost)
    # Pass A 에서 *높은 신뢰* PERSON 이 잡힌 문장의 *약한 후보* 들도 +0.15
    # 보강 후 임계값 재평가.
    sentence_boundaries = _find_sentence_boundaries(text)
    strong_sentence_ids: set[int] = set()
    for cand, _p, score_v, _ev in emitted:
        if score_v >= 0.70:
            sid = _sentence_id(cand.start, sentence_boundaries)
            strong_sentence_ids.add(sid)

    co_boosted: list[tuple] = []
    still_pending: list[tuple] = []
    for cand, score_v, ev, particle in pending:
        sid = _sentence_id(cand.start, sentence_boundaries)
        if sid in strong_sentence_ids:
            boosted_score = min(1.0, score_v + 0.15)
            boosted_ev = list(ev) + ["pos:co_occurrence_in_sentence"]
            if boosted_score >= threshold:
                co_boosted.append((cand, particle, boosted_score, boosted_ev))
                name_dict.add(cand.name, boosted_score,
                              (cand.start, cand.end), boosted_ev)
                continue
        still_pending.append((cand, score_v, ev, particle))

    # 모두 emit
    for cand, particle, score_v, ev in emitted + co_boosted:
        yield _emit(cand, particle, score_v, ev)

    # ------ Pass B: re-score remaining pending using the now-populated dictionary
    for cand, _score_a, ev_a, particle in still_pending:
        boost = name_dict.boost_for(cand.name)
        if boost <= 0:
            continue
        rescored = score_candidate(
            text, cand,
            deterministic_nearby=_is_within(
                deterministic_spans, cand.start, window=25
            ),
            name_dictionary_boost=boost,
            agency_cache=_agency_cache,
        )
        if rescored.value >= threshold:
            yield _emit(cand, particle, rescored.value, rescored.evidence)


from ko_pii.dictionaries.field_labels import FIELD_LABELS_NAME


def _label_before(text: str, start: int) -> bool:
    head = text[max(0, start - 10): start]
    return any(lbl in head for lbl in FIELD_LABELS_NAME)


def _is_within(
    spans: Iterable[tuple[int, int]], pos: int, window: int = 25
) -> bool:
    for s, e in spans:
        if abs(s - pos) <= window or abs(e - pos) <= window:
            return True
    return False


def _emit(
    cand: NameCandidate,
    particle: str | None,
    score: float,
    evidence: list[str],
) -> DetectionResult:
    origin = classify_name_origin(cand.name)
    return DetectionResult(
        label=LABEL,
        text=cand.name,
        start=cand.start,
        end=cand.end,
        risk_level=RiskLevel.HIGH,
        confidence=score,
        evidence=evidence + [f"origin:{origin}"],
        legal_basis=LEGAL_BASIS,
        extra={
            "category": CATEGORY,
            "particle": particle,
            "origin": origin,
        },
    )


# ---------------------------------------------------------------------
# Method 2 보조: 문장 경계 (마침표·줄바꿈·물음표·느낌표)
# ---------------------------------------------------------------------

def _find_sentence_boundaries(text: str) -> list[int]:
    """Return list of sentence start offsets (sorted)."""
    starts = [0]
    for i, ch in enumerate(text):
        if ch in ".!?\n":
            if i + 1 < len(text):
                starts.append(i + 1)
    return starts


def _sentence_id(pos: int, boundaries: list[int]) -> int:
    """Return the sentence index (0-based) containing `pos`."""
    import bisect
    idx = bisect.bisect_right(boundaries, pos) - 1
    return max(0, idx)
