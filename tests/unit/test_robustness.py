"""견고성 — 비공격 엣지 입력에 크래시/hang 없이 fail-safe, non-str 은 명확한 TypeError."""
from __future__ import annotations

import pytest

from ko_pii import detect_all

EDGE = ["", "   \t\n ", "\x00", "\x01\x02\x03", "가" * 20000, "\n" * 5000,
        "🔥" * 500, "abc\ud800def", "́́́", "‮abc‬ 900101-1234567"]


@pytest.mark.parametrize("x", EDGE, ids=lambda v: repr(v[:12]))
def test_edge_input_no_crash(x: str) -> None:
    assert isinstance(detect_all(x), list)


@pytest.mark.parametrize("bad", [None, 123, b"x", ["l"], {"d": 1}])
def test_non_str_raises_typeerror(bad: object) -> None:
    with pytest.raises(TypeError):
        detect_all(bad)  # type: ignore[arg-type]
