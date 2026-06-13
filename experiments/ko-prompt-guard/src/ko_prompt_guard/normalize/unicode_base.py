"""기본 유니코드 정규화 — 보이지 않는 문자 제거 + 클러스터 NFKC.

ko-pii ``core/unicode_norm.py`` 에서 이식(MIT, 동일 저자). 두 가지로 분리한다:
- ``strip_invisible`` : 제로폭/제어/방향 문자 제거
- ``nfkc_fold``       : 전각/호환문자/NFD 분해형을 글자 클러스터 단위로 NFKC 합성

★ 핵심: NFKC 는 한글 호환자모(ㅋ U+314B)를 조합자모(ᄏ U+110F)로 분해해 정상
'ㅋㅋ'를 깨뜨리므로, 호환자모(U+3131~U+318E)는 NFKC 대상에서 제외한다. 그 영역은
파이프라인 앞단의 ``jamo.combine_jamo`` 가 음절 결합으로 처리하고, 남은 단독
자모(ㅋㅋ/ㅠㅠ)는 그대로 보존된다. stdlib only.
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f"
    r"­​-‏‪-‮⁠-⁯⩴﻿"
    r"ᅟᅠㅤﾠ]"  # 한글 필러(빈칸 렌더링) — 칸별 분리 우회 '이ㅤ전ㅤ지'
)

_COMBINING = re.compile(
    r"[̀-ͯ҃-҉֑-ֽؐ-ؚ"
    r"ً-ٰٟۖ-ۜ᪰-᫿᷀-᷿"
    r"⃐-⃿︠-︯]"
)


def needs_normalization(text: str) -> bool:
    """정규화(우회 차단)가 필요한가 — 비ASCII이거나 제어/보이지 않는 문자 포함."""
    return (not text.isascii()) or bool(_INVISIBLE.search(text))


def _is_conjoining_jamo(ch: str) -> bool:
    """NFD 분해형 한글 자모(초성/중성/종성) — 합성 클러스터에 포함."""
    return "ᄀ" <= ch <= "ᇿ" or "ꥠ" <= ch <= "꥿" or "ힰ" <= ch <= "퟿"


def _is_compat_jamo(ch: str) -> bool:
    """호환 자모(U+3131~U+318E) — NFKC 보존(combine_jamo 가 담당)."""
    return "ㄱ" <= ch <= "ㆎ"


def strip_invisible(text: str) -> str:
    return _INVISIBLE.sub("", text)


def nfkc_fold(text: str) -> str:
    """클러스터 단위 NFKC. 호환자모는 보존(NFKC 분해로 인한 'ㅋㅋ' 파괴 방지)."""
    if not _COMBINING.search(text) and unicodedata.is_normalized("NFKC", text):
        return text
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _is_compat_jamo(ch):
            out.append(ch)  # 호환자모 보존
            i += 1
            continue
        j = i + 1
        while j < n and (unicodedata.combining(text[j]) or _is_conjoining_jamo(text[j])):
            j += 1
        # 한국어 프롬프트 가드: 글자에 덧붙은 결합표시(U+0300 등)는 정상 한글에 거의
        # 없고 '시̀스̀템̀'/'i̥g̥n̥o̥r̥e̥' 처럼 토큰을 쪼개는 우회 신호다 → 항상 제거.
        # NFKC 만으로는 precomposed 형(ḁ=U+1E01)이 안 펴지므로 NFD 로 분해해 결합표시를
        # 떼고 NFC 로 재조합한다. 한글 음절은 conjoining jamo 로 분해되나 combining()==0
        # 이라 보존된다(PII 가드 ko-pii 와 달리 라틴 diacritic 보존은 불필요).
        nfd = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text[i:j]))
        stripped = "".join(c for c in nfd if not unicodedata.combining(c))
        out.append(unicodedata.normalize("NFC", stripped))
        i = j
    return "".join(out)
