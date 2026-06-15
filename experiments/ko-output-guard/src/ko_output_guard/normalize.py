"""난독 출력 정규화 — 한국어 detector(toxicity/unsafe/prompt-leak) 검사 전처리.

jailbreak 된 모델은 욕설/위험 권고를 초성화·제로폭·전각·homoglyph 로 흩뜨려 출력할
수 있다. ko-prompt-guard 가 설치돼 있으면 그 강력한 정규화(자모결합·초성·전각·
homoglyph·splitting·leet)를 재사용하고, 없으면 경량 fallback(제로폭 제거 + 글자별
NFKC)을 쓴다. 형식이 보존돼야 하는 SECRET/PII detector 는 원본에서 검사하므로 이
함수를 거치지 않는다(정규화로 토큰/PII 형식이 깨지면 안 됨).
"""
from __future__ import annotations

import re
import unicodedata

_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁯﻿­]")


def _light_fallback(text: str) -> str:
    t = _INVISIBLE.sub("", text)
    # 글자별 NFKC(전각/호환문자 → ASCII). 단 한글 호환자모(ㅅㅂ/ㅋㅋ)는 NFKC 가
    # 조합자모로 분해해 깨뜨리므로 보존한다(욕설 초성 'ㅅㅂ' 탐지 유지).
    return "".join(
        ch if "㄰" <= ch <= "㆏" else unicodedata.normalize("NFKC", ch)
        for ch in t
    )


def normalize_for_detection(text: str) -> str:
    try:
        from ko_prompt_guard import GuardPolicy
        from ko_prompt_guard.normalize import normalize

        return str(normalize(text, GuardPolicy())[0])
    except ImportError:
        return _light_fallback(text)
