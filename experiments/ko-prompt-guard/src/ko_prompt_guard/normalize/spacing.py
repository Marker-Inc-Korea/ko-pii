"""칸별 분리 우회 축약 — 단일 글자가 공백/점/하이픈/쉼표/밑줄/개행으로 흩뿌려진
토막을 합친다.

'무 시 해' / '무.시.해' / '무-시-해' / 'i,g,n,o,r,e' / 'i_g_n_o_r_e' → 합침. 정상
단어 공백('… 주세요')·나열('가, 나, 다': 구분자에 공백 동반)·식별자('snake_case':
토막이 단어)는 보존한다 (단일 글자가 2회 이상 같은 류 구분자로 분리된 런만 대상).
"""
from __future__ import annotations

import re

_CH = r"[가-힣A-Za-z0-9]"
# 점·중점·하이픈·쉼표·밑줄로 분리(공백 없는 구분자). 쉼표/밑줄은 단일 글자 런에서만
# 작용하므로 'a, b'(쉼표+공백 나열)·'my_var'(단어 토막)는 매칭되지 않는다.
_PUNCT = r"[.·‧\-,_]"
_DOT_SEP = re.compile(rf"{_CH}(?:{_PUNCT}{_CH}){{2,}}")
# 공백류(스페이스/탭/개행)로 분리된 단일 글자 런. 뒤가 또 글자면(=정상 단어) 끊는다.
_WS = r"[ \t\r\n]"
_SPACE_SEP = re.compile(rf"(?:{_CH}{_WS}){{2,}}{_CH}(?!{_CH})")


def collapse_separators(text: str) -> str:
    text = _DOT_SEP.sub(lambda m: re.sub(_PUNCT, "", m.group(0)), text)
    text = _SPACE_SEP.sub(lambda m: re.sub(_WS, "", m.group(0)), text)
    return text
