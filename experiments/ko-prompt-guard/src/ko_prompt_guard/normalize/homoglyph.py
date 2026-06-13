"""유니코드 호몰로그(confusable) 폴딩 — mixed-script 토큰만 (정규화 단계 4).

키릴/그리스 글리프를 닮은꼴 라틴으로 펴되, 토큰이 두 개 이상 스크립트를 섞었을
때만 적용한다 → 정상 러시아어/그리스어 문장(단일 스크립트)은 파괴하지 않는다.
코드포인트는 UTS#39 confusables 기반(util.unicode.org 검증). stdlib only.
"""
from __future__ import annotations

import re
import unicodedata

# 키릴 → 라틴 (확실한 동형 위주; 일부 근사는 주석)
CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a", "о": "o", "е": "e", "р": "p", "с": "c", "у": "y", "х": "x",
    "к": "k", "м": "m", "т": "t", "в": "b", "н": "h", "і": "i", "ј": "j",
    "ѕ": "s", "ӏ": "l", "ԁ": "d", "ԛ": "q", "ԝ": "w", "є": "e",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X", "І": "I", "Ј": "J",
    "Ѕ": "S", "г": "r", "п": "n",
}

# 그리스 → 라틴
GREEK_TO_LATIN: dict[str, str] = {
    "ο": "o", "α": "a", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "κ": "k",
    "ι": "i", "η": "n", "γ": "y", "χ": "x", "μ": "u",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "β": "B",
}

HOMOGLYPH_TO_LATIN: dict[str, str] = {**CYRILLIC_TO_LATIN, **GREEK_TO_LATIN}

# 한글 자모 닮은꼴 — UTS#39 밖, 정상 'ㅇㅇ'/'ㅋㅋ' 파괴 위험 → 기본 OFF.
HANGUL_TO_LATIN: dict[str, str] = {"ㅇ": "O", "ㅣ": "l", "ㅡ": "-", "ㄱ": "r", "ㄴ": "L"}

_SCRIPT_BY_RANGE: tuple[tuple[int, int, str], ...] = (
    (0x0041, 0x005A, "LATIN"), (0x0061, 0x007A, "LATIN"), (0x00C0, 0x024F, "LATIN"),
    (0x1E00, 0x1EFF, "LATIN"), (0xFF21, 0xFF3A, "LATIN"), (0xFF41, 0xFF5A, "LATIN"),
    (0x0370, 0x03FF, "GREEK"), (0x1F00, 0x1FFF, "GREEK"),
    (0x0400, 0x04FF, "CYRILLIC"), (0x0500, 0x052F, "CYRILLIC"),
    (0x2DE0, 0x2DFF, "CYRILLIC"), (0xA640, 0xA69F, "CYRILLIC"),
    (0xAC00, 0xD7A3, "HANGUL"), (0x1100, 0x11FF, "HANGUL"), (0x3130, 0x318F, "HANGUL"),
    (0xA960, 0xA97F, "HANGUL"), (0xD7B0, 0xD7FF, "HANGUL"),
    (0x3040, 0x30FF, "KANA"), (0x4E00, 0x9FFF, "HAN"), (0x3400, 0x4DBF, "HAN"),
)

_WS_SPLIT = re.compile(r"(\s+)")


def char_script(ch: str) -> str | None:
    """문자 1개의 스크립트 추정. 숫자/기호/공백 등 폴딩 무관 문자는 None."""
    if not ch:
        return None
    cat = unicodedata.category(ch)
    if cat[0] != "L" and cat not in ("Mn", "Mc"):
        return None
    cp = ord(ch)
    for lo, hi, name in _SCRIPT_BY_RANGE:
        if lo <= cp <= hi:
            return name
    try:
        nm = unicodedata.name(ch)
    except ValueError:
        return "OTHER"
    for key in ("LATIN", "GREEK", "CYRILLIC", "HANGUL", "CJK", "HIRAGANA", "KATAKANA"):
        if nm.startswith(key):
            return "HAN" if key == "CJK" else key
    return "OTHER"


def token_scripts(token: str) -> set[str]:
    return {s for s in (char_script(c) for c in token) if s is not None}


def is_mixed_script(token: str) -> bool:
    """토큰 안에 2개 이상의 글자 스크립트가 섞였으면 True (호몰로그 공격 신호)."""
    return len(token_scripts(token)) >= 2


def _fold_token(token: str, *, fold_hangul: bool) -> str:
    if not is_mixed_script(token):
        return token
    out: list[str] = []
    for ch in token:
        if ch in HOMOGLYPH_TO_LATIN:
            out.append(HOMOGLYPH_TO_LATIN[ch])
        elif fold_hangul and ch in HANGUL_TO_LATIN:
            out.append(HANGUL_TO_LATIN[ch])
        else:
            out.append(ch)
    return "".join(out)


def fold_homoglyphs(text: str, *, fold_hangul: bool = False) -> str:
    """텍스트를 공백 토큰 단위로 조건부 폴딩. mixed-script 토큰만 변형한다."""
    parts = _WS_SPLIT.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _fold_token(parts[i], fold_hangul=fold_hangul)
    return "".join(parts)
