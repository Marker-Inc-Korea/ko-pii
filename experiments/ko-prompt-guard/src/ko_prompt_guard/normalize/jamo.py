"""호환자모열 → 완성형 음절 결합 (난독 공격 'ㅈㅜ'→'주' 복원). stdlib only.

정상 한국어 보호가 핵심: ㅋㅋ/ㅠㅠ/ㄱㅅ/목록마커(ㄱ.)는 음절을 형성하지 못하므로
결합하지 않는다. 종성은 lookahead("뒤에 모음이 더 있으면 다음 음절 초성으로 양보")로
판정한다. jamo/hgtk 라이브러리 없이 0xAC00 산술로 합성한다.
"""
from __future__ import annotations

import re

CHOSEONG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")  # 19
JUNGSEONG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")  # 21
JONGSEONG = ["", *list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")]  # idx0=받침없음

CHO_IDX: dict[str, int] = {c: i for i, c in enumerate(CHOSEONG)}
JUNG_IDX: dict[str, int] = {c: i for i, c in enumerate(JUNGSEONG)}
JONG_IDX: dict[str, int] = {c: i for i, c in enumerate(JONGSEONG) if c}  # 1..27

# 분리된 두 단자음 → 단일 종성 (예: ㄹ+ㄱ → ㄺ)
DOUBLE_JONG: dict[tuple[str, str], str] = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ", ("ㄹ", "ㄱ"): "ㄺ",
    ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ",
    ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ",
}

_S_BASE, _N_JUNG, _N_JONG = 0xAC00, 21, 28
_MARKER_RE = re.compile(r"^[ㄱ-ㅎ][.)、．）]")  # 목록마커 'ㄱ.' 보호


def _is_compat_jamo(ch: str) -> bool:
    return "ㄱ" <= ch <= "ㆎ"  # U+3131~U+318E


def can_be_cho(ch: str) -> bool:
    return ch in CHO_IDX


def can_be_jung(ch: str) -> bool:
    return ch in JUNG_IDX


def can_be_jong(ch: str) -> bool:
    return ch in JONG_IDX


def compose_syllable(cho: str, jung: str, jong: str = "") -> str:
    ci, vi = CHO_IDX[cho], JUNG_IDX[jung]
    ti = JONG_IDX.get(jong, 0) if jong else 0
    return chr(_S_BASE + (ci * _N_JUNG + vi) * _N_JONG + ti)


def _scan_run(s: str, i: int) -> int:
    j = i
    while j < len(s) and _is_compat_jamo(s[j]):
        j += 1
    return j


def compose_jamo_run(run: str) -> str:
    """연속 호환자모 run → 음절 결합. 결합 불가하면 원문 보존."""
    out: list[str] = []
    i, n = 0, len(run)
    while i < n:
        ch = run[i]
        if not can_be_cho(ch):
            out.append(ch)  # 모음 시작 → 초성 없음 → 보호(ㅠㅠ/ㅜㅜ)
            i += 1
            continue
        if i + 1 < n and can_be_jung(run[i + 1]):
            cho, jung = ch, run[i + 1]
            jong, consumed, k = "", 2, i + 2
            if k + 1 < n and (run[k], run[k + 1]) in DOUBLE_JONG:
                after = run[k + 2] if k + 2 < n else ""
                if not (after and can_be_jung(after)):
                    jong, consumed = DOUBLE_JONG[(run[k], run[k + 1])], 4  # 닭/값/없다
                else:
                    jong, consumed = run[k], 3  # 겹받침 뒤 모음 → 둘째 자음은 다음 초성
            elif k < n and can_be_jong(run[k]):
                cand = run[k]
                nxt = run[k + 1] if k + 1 < n else ""
                if not (nxt and can_be_jung(nxt)):
                    has_vowel_ahead = any(can_be_jung(run[m]) for m in range(k + 1, n))
                    if has_vowel_ahead or k == n - 1:
                        jong, consumed = cand, 3
            out.append(compose_syllable(cho, jung, jong))
            i += consumed
        else:
            out.append(ch)  # 초성+중성없음 → 자음연속 보호(ㅋㅋ/ㄱㅅ/ㄷㄷ)
            i += 1
    return "".join(out)


def combine_jamo(text: str) -> str:
    """텍스트의 호환자모 run을 음절로 결합. 비자모·목록마커는 보존."""
    res: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if _is_compat_jamo(ch):
            if _MARKER_RE.match(text[i : i + 2]):
                res.append(ch)
                i += 1
                continue
            j = _scan_run(text, i)
            res.append(compose_jamo_run(text[i:j]))
            i = j
        else:
            res.append(ch)
            i += 1
    return "".join(res)
