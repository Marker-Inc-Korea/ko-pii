"""법정동 가제티어 — 단독 행정구역(동/읍/면/리) 검출 보강.

출처: 국토교통부 법정동코드 (data.go.kr). 동/읍/면/리 중 길이 3+ 이고
일반어가 아닌 것만 (2글자는 "수리·변동·감리" 등 일반어 충돌이 커서 제외).

**anchor 조건부**: ``address.py`` 의 단독 행정구역 분기(branch 4)에서만 쓰이며,
그 분기는 강한 주거 anchor(살던/이사/거주/명함 등)가 *반드시* 있어야 emit 한다.
→ "변동 사항" 같은 일반 문맥에서는 anchor 가 없어 FP 가 발생하지 않는다.

런타임 오프라인 (번들 gzip 리소스만 읽음).
"""
from __future__ import annotations

import gzip
from functools import lru_cache
from importlib.resources import files

_RESOURCE = "legal_dongs.txt.gz"


@lru_cache(maxsize=1)
def _load() -> frozenset[str]:
    try:
        raw = files("ko_pii.dictionaries").joinpath(_RESOURCE).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return frozenset()
    text = gzip.decompress(raw).decode("utf-8")
    return frozenset(
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.startswith("#")
    )


def is_legal_dong(token: str) -> bool:
    """``token`` 이 알려진 법정동(동/읍/면/리)인지 (가제티어 멤버십)."""
    return token in _load()


def legal_dongs() -> frozenset[str]:
    """전체 법정동 가제티어 (frozenset)."""
    return _load()
