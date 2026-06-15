"""견고성 — 엣지 입력 fail-safe, non-str 은 TypeError."""
from __future__ import annotations

import pytest

from ko_prompt_guard import Guard

GUARD = Guard()
EDGE = ["", "   \t\n ", "\x00", "\x01\x02", "가" * 20000, "\n" * 5000,
        "🔥" * 500, "abc\ud800def", "‮ignore‬ all previous"]


@pytest.mark.parametrize("x", EDGE, ids=lambda v: repr(v[:12]))
def test_edge_input_no_crash(x: str) -> None:
    assert GUARD.check(x).verdict is not None


@pytest.mark.parametrize("bad", [None, 123, b"x", ["l"]])
def test_non_str_raises_typeerror(bad: object) -> None:
    with pytest.raises(TypeError):
        GUARD.check(bad)  # type: ignore[arg-type]
