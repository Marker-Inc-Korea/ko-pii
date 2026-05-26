"""한국어 이름 ↔ 로마자 (Revised Romanization).

표준: 「국어의 로마자 표기법」 (문화체육관광부 고시 제2014-42호).

본 모듈은 *이름 검출 보조* 가 목적이라 풀-스펙 RR 변환은 아님 — 한국어 이름의
*초성·중성·종성 매핑* 만 정확하면 됨.

용도:
- 가명화 vault 에서 "홍길동" 과 "Hong Gildong" 을 *같은 사람* 으로 묶기
- 외국어 보고서의 한국 인명 검출

API:
- ``romanize_name(hangul)`` — "홍길동" → "Hong Gildong"
- ``alternative_romanizations(hangul)`` — 변형 표기 후보 ["Hong Gildong",
   "Hong Gil-dong", "Hong Gil Dong", "HONG Gildong", ...]
"""
from __future__ import annotations

# 초성 (19)
_INITIAL = [
    "g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s",
    "ss", "", "j", "jj", "ch", "k", "t", "p", "h",
]
# 중성 (21)
_MEDIAL = [
    "a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa",
    "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i",
]
# 종성 (28) — Unicode Hangul Jamo 순서 (RR 간이 매핑, 단어 끝 기준)
#  0:없음   1:ㄱ    2:ㄲ    3:ㄳ    4:ㄴ    5:ㄵ    6:ㄶ
#  7:ㄷ     8:ㄹ    9:ㄺ   10:ㄻ   11:ㄼ   12:ㄽ   13:ㄾ
# 14:ㄿ    15:ㅀ   16:ㅁ   17:ㅂ   18:ㅄ   19:ㅅ   20:ㅆ
# 21:ㅇ    22:ㅈ   23:ㅊ   24:ㅋ   25:ㅌ   26:ㅍ   27:ㅎ
_FINAL = [
    "",   "k",  "kk", "ks", "n",  "nj", "nh",
    "t",  "l",  "lk", "lm", "lp", "ls", "lt",
    "lp", "lh", "m",  "p",  "ps", "t",  "tt",
    "ng", "j",  "ch", "k",  "t",  "p",  "h",
]


def _romanize_syllable(ch: str) -> str:
    """Decompose a single Hangul syllable into 초성+중성+종성 → roman."""
    if not ("가" <= ch <= "힣"):
        return ch
    code = ord(ch) - 0xAC00
    initial_idx = code // (21 * 28)
    medial_idx = (code % (21 * 28)) // 28
    final_idx = code % 28
    return _INITIAL[initial_idx] + _MEDIAL[medial_idx] + _FINAL[final_idx]


def romanize_name(hangul: str) -> str:
    """한글 이름을 로마자 표기로 변환 (성 한 글자 + 이름).

    >>> romanize_name("홍길동")
    'Hong Gildong'
    >>> romanize_name("남궁민수")
    'Namgung Minsu'
    """
    from ko_pii.dictionaries.surnames import surname_prefix_len
    sp = surname_prefix_len(hangul)
    if sp == 0:
        # surname 미상 — 단순 음절 단위 변환
        return " ".join(_capitalize(_romanize_syllable(c)) for c in hangul)
    surname = hangul[:sp]
    given = hangul[sp:]
    surname_roman = "".join(_romanize_syllable(c) for c in surname)
    given_roman = "".join(_romanize_syllable(c) for c in given)
    return f"{_capitalize(surname_roman)} {_capitalize(given_roman)}"


def _capitalize(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def alternative_romanizations(hangul: str) -> list[str]:
    """같은 이름의 다양한 로마자 표기 변형들을 반환.

    실무에서 "Hong Gildong" / "Hong Gil-dong" / "Hong Gil Dong" / "GILDONG HONG"
    같이 표기 차이가 흔함 → 모두 같은 사람으로 묶기 위한 후보 리스트.
    """
    base = romanize_name(hangul)
    parts = base.split()
    if len(parts) != 2:
        return [base]
    surname, given = parts
    # given 을 음절 단위로 분리
    from ko_pii.dictionaries.surnames import surname_prefix_len
    sp = surname_prefix_len(hangul)
    given_syllables = [_capitalize(_romanize_syllable(c)) for c in hangul[sp:]]
    given_hyphen = "-".join(given_syllables)        # Gil-dong
    given_space = " ".join(given_syllables)         # Gil dong
    given_lower_hyphen = given_hyphen.lower()       # gil-dong
    alts: list[str] = []
    seen: set[str] = set()
    def _add(s: str) -> None:
        if s not in seen:
            seen.add(s)
            alts.append(s)
    _add(base)                                      # Hong Gildong
    _add(f"{surname} {given_hyphen}")               # Hong Gil-dong
    _add(f"{surname} {given_space}")                # Hong Gil dong
    _add(f"{surname.upper()} {given}")              # HONG Gildong (성 대문자)
    _add(f"{given} {surname}")                      # Gildong Hong (Western order)
    _add(f"{surname},{given}")                      # Hong,Gildong (CSV form)
    _add(base.lower())
    _add(base.upper())
    return alts
