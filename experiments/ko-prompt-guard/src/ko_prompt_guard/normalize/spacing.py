"""칸별 분리 우회 축약 — 단일 글자가 공백/점/하이픈으로 흩뿌려진 토막을 합친다.

'무 시 해' / '무.시.해' / '무-시-해' → '무시해'. 정상 단어 공백('… 주세요')과
문장부호는 보존한다 (단일 글자가 2회 이상 같은 구분자로 분리된 런만 대상).
"""
from __future__ import annotations

import re

_CH = r"[가-힣A-Za-z0-9]"

# 점·중점·하이픈으로 분리된 단일 글자 런 (2회 이상 구분).
_DOT_SEP = re.compile(rf"{_CH}(?:[.·‧\-]{_CH}){{2,}}")
# 공백으로 분리된 단일 글자 런. 다음 글자가 또 글자로 이어지면(=정상 단어) 끊는다.
_SPACE_SEP = re.compile(rf"(?:{_CH} ){{2,}}{_CH}(?!{_CH})")


def collapse_separators(text: str) -> str:
    text = _DOT_SEP.sub(lambda m: re.sub(r"[.·‧\-]", "", m.group(0)), text)
    text = _SPACE_SEP.sub(lambda m: m.group(0).replace(" ", ""), text)
    return text
