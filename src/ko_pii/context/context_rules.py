"""컨텍스트 점수 시스템 — 이름 후보 평가.

각 후보는 0.0~1.0 사이 점수를 받고, 임계값 이상이면 PERSON 으로 emit.

점수 가산 신호:
+ 0.50  필드 라벨 (성명: / 신청인) 가 직전(≤4자) 에 있음
+ 0.35  공무원·민간 직책이 인접(≤3자) — 앞 또는 뒤
+ 0.30  결정적 PII (RRN/PHONE/EMAIL) 가 동일 문장 내 인접
+ 0.20  한국어 조사 (이/가/은/는/을/를) 가 직접 붙음
+ 0.15  성씨 사전 매칭
+ 0.10  기관(부처/기관) 토큰이 같은 문장 내
+ 0.20  누적 사전에 이미 확정된 이름

감점 신호:
- 0.40  토큰이 일반 단어 사전에 있음
- 0.30  토큰 길이 1 (한 글자 이름은 시드 신호 없으면 거의 항상 FP)
- 0.20  토큰이 숫자/영문 포함
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ko_pii.dictionaries.common_words import is_common_word
from ko_pii.dictionaries.surnames import surname_prefix_len
from ko_pii.dictionaries.titles import is_title, is_gov_title
from ko_pii.dictionaries.agencies import is_agency


@dataclass
class NameCandidate:
    name: str
    start: int
    end: int


@dataclass
class Score:
    value: float
    evidence: list[str] = field(default_factory=list)


def _has_field_label_before(text: str, start: int, window: int = 6) -> str | None:
    """Look for a name-field label like "성명:" within ``window`` chars before."""
    from ko_pii.dictionaries.field_labels import FIELD_LABELS_NAME
    head = text[max(0, start - window - 4): start]
    # Strip whitespace and common separators
    for label in FIELD_LABELS_NAME:
        # Allow "성명:", "성명 :", "성명 ", etc.
        idx = head.rfind(label)
        if idx == -1:
            continue
        between = head[idx + len(label):]
        stripped = between.strip().lstrip(":：").strip()
        if stripped == "":
            return label
    return None


def _has_title_adjacent(text: str, start: int, end: int, window: int = 5) -> tuple[str | None, bool]:
    """Return ``(matched_title, is_gov)`` if a title is within ``window`` chars.

    Checks both sides: "<title> <name>" and "<name> <title>". Korean
    particles attached to the title (e.g. "과장이", "과장은") are stripped
    before lookup. Connective endings (e.g. "주임이며/주임이고") are
    also stripped by checking title prefix.
    """
    from ko_pii.context.particles import strip_trailing_particle

    def _resolve_title(word: str) -> tuple[str | None, bool]:
        """word → title 정식형 (조사·연결어미 제거 후 dict 매칭)."""
        # 1차: 조사 strip 후 dict 매칭
        stem, _ = strip_trailing_particle(word)
        if is_title(stem):
            return stem, is_gov_title(stem)
        # 2차: 직책 dict 의 prefix 매칭 (조사·연결어미 부착 형식)
        # "주임이며/주임이고/주임이라/사장님은" 같은 패턴 cover
        # 가장 긴 매칭 우선 (4자 → 2자)
        for plen in range(min(len(stem), 5), 1, -1):
            prefix = stem[:plen]
            if is_title(prefix):
                return prefix, is_gov_title(prefix)
        return None, False

    # After the candidate (most common: "홍길동 과장")
    tail = text[end: end + window + 6]
    for word in _word_iter(tail):
        title, gov = _resolve_title(word)
        if title is not None:
            return title, gov
        break  # only the first word counts as "adjacent"

    # Before the candidate (e.g., "과장 홍길동")
    head_start = max(0, start - window - 6)
    head = text[head_start: start]
    rev = head.rstrip()
    if rev:
        last = rev.split()[-1]
        title, gov = _resolve_title(last)
        if title is not None:
            return title, gov
    return None, False


def _has_agency_in_sentence(text: str, start: int, end: int) -> bool:
    # Extract sentence boundaries: . / 다. / 음. / line break
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
    right_dot = text.find(".", end)
    right_nl = text.find("\n", end)
    candidates = [r for r in (right_dot, right_nl) if r != -1]
    right = min(candidates) if candidates else len(text)
    sentence = text[left:right]
    for tok in _word_iter(sentence):
        if is_agency(tok):
            return True
    return False


def _has_particle_attached(text: str, end: int) -> str | None:
    """Check if right after the candidate there is a Korean particle."""
    from ko_pii.context.particles import PARTICLES
    tail = text[end: end + 3]
    for p in PARTICLES:
        if tail.startswith(p):
            return p
    return None


def _word_iter(text: str):
    import re
    for m in re.finditer(r"\S+", text):
        yield m.group(0)


def _looks_korean(name: str) -> bool:
    return all("가" <= ch <= "힣" for ch in name)


def score_candidate(
    text: str,
    cand: NameCandidate,
    deterministic_nearby: bool = False,
    name_dictionary_boost: float = 0.0,
) -> Score:
    """Compute a 0~1 score for ``cand`` based on surrounding signals."""
    ev: list[str] = []
    score = 0.0

    # Negative signal: common word.
    if is_common_word(cand.name):
        score -= 0.40
        ev.append("neg:common_word")

    # Negative signal: non-Korean characters.
    if not _looks_korean(cand.name):
        score -= 0.20
        ev.append("neg:non_korean")

    # Negative signal: length 1.
    if len(cand.name) == 1:
        score -= 0.30
        ev.append("neg:length_1")

    # Surname presence
    sp = surname_prefix_len(cand.name)
    if sp > 0:
        score += 0.15
        ev.append(f"pos:surname({cand.name[:sp]})")

    # Field label immediately before
    label = _has_field_label_before(text, cand.start)
    if label:
        score += 0.50
        ev.append(f"pos:field_label({label})")

    # Title adjacency
    title, gov = _has_title_adjacent(text, cand.start, cand.end)
    if title:
        score += 0.35
        ev.append(f"pos:title({title}{':gov' if gov else ''})")

    # Particle attached — 한국어의 강한 PERSON 신호
    # 예: "장혁이 울었다" → surname + particle 만으로도 인명 인식 가능해야
    p = _has_particle_attached(text, cand.end)
    if p:
        score += 0.35
        ev.append(f"pos:particle({p})")

    # Deterministic PII adjacent — strong cue: RRN/PHONE next to a Korean
    # 2~4 char surname-prefixed token is almost always a name.
    # 길이 차등 부스트 (KDPII 과탐 분석 결과):
    # - 3자+ 풀네임: +0.40 (확정적 PII 옆 풀네임 = 거의 확실한 인명)
    # - 2자 단명·약명: +0.20 (성+1자 이름은 일반 어휘 충돌 잦음)
    if deterministic_nearby:
        token_len = cand.end - cand.start
        boost = 0.40 if token_len >= 3 else 0.20
        score += boost
        ev.append("pos:deterministic_pii_nearby")

    # Agency mention in same sentence
    if _has_agency_in_sentence(text, cand.start, cand.end):
        score += 0.10
        ev.append("pos:agency_in_sentence")

    # Cumulative dictionary boost
    if name_dictionary_boost > 0:
        score += name_dictionary_boost
        ev.append(f"pos:name_dict_boost({name_dictionary_boost:.2f})")

    # Clamp to [0, 1]
    if score < 0:
        score = 0.0
    if score > 1:
        score = 1.0
    return Score(value=score, evidence=ev)
