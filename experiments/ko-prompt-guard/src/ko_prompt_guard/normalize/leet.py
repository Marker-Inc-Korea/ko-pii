"""Leetspeak 숫자→문자 디코드 (보수적, detection 보강 전용).

'1gn0r3 4ll pr3v10us'처럼 글자를 숫자로 바꾼 우회를 펴기 위한 보조 변환이다.
정규화 파이프라인에는 넣지 않는다 — '버전 3'·'mp3'·'2024' 같은 정상 토큰까지
바꿔 was_obfuscated/FLAG 과탐을 유발하기 때문. guard 에서 별도로 디코드본을 한 번
더 스캔해 '추가로' 잡히는 공격만 더한다(원본 판정/FLAG 에는 영향 없음).

토큰 게이팅: ASCII 알파벳과 숫자가 한 토큰에 함께 있을 때만 치환한다. 그래서
순수 숫자('2024')·순수 글자('ignore')·한글+숫자('버전3')는 건드리지 않는다.
"""
from __future__ import annotations

import re

# 보수적 매핑(흔한 leet 만). 1→i, l 혼동은 i 로 통일.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"})
_TOKEN = re.compile(r"[A-Za-z0-9]+")


def _decode_token(tok: str) -> str:
    has_alpha = any(c.isalpha() and c.isascii() for c in tok)
    has_digit = any(c.isdigit() for c in tok)
    return tok.translate(_LEET) if (has_alpha and has_digit) else tok


def deleet(text: str) -> str:
    """ASCII 알파벳+숫자 혼합 토큰의 leet 숫자를 글자로 되돌린다."""
    return _TOKEN.sub(lambda m: _decode_token(m.group(0)), text)
