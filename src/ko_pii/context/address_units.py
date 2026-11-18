"""Shared continuations after typed address units, without consuming the tail."""
from __future__ import annotations

import re


_LONG_PARTICLE = r"(?:으로부터|에서부터|으로|에서|부터|까지)"
_SHORT_PARTICLE = r"(?:에|로|은|는|이|가|을|를|도|만|의)(?:은|는|도|만|의)?(?=[\W_]|$)"
_COPULA = r"(?:입니다|이에요|이었|이다|이고|이며|이라|이어서|예요)"
_BOUNDARY_OR_PARTICLE = r"(?:[\W_]|$|" + _LONG_PARTICLE + "|" + _SHORT_PARTICLE + "|" + _COPULA + ")"
_LOCATION_NOUN = (
    r"(?:근처|인근|주변|내부|외부|출입구|입구|출구|로비|사무실|상가|"
    r"안쪽|바깥쪽|바깥|앞쪽|뒤쪽|옆쪽|맞은편|건너편|동쪽|서쪽|남쪽|북쪽)"
    r"(?=" + _BOUNDARY_OR_PARTICLE + ")"
)
_SHORT_LOCATION = r"(?:앞|뒤|옆|안|내)(?=" + _BOUNDARY_OR_PARTICLE + "|" + _LOCATION_NOUN + ")"
UNIT_TAIL = r"(?:" + _BOUNDARY_OR_PARTICLE + "|" + _LOCATION_NOUN + "|" + _SHORT_LOCATION + ")"
_TAIL_PATTERN = re.compile(UNIT_TAIL)


def has_unit_tail(text: str, position: int) -> bool:
    return _TAIL_PATTERN.match(text, position) is not None
