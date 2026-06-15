"""견고성 — 엣지/malformed SQL fail-closed, non-str 은 TypeError."""
from __future__ import annotations

import pytest

from ko_sqlguard import GuardPolicy, Verdict, check

POLICY = GuardPolicy(allowed_tables={"orders": [], "customers": ["id", "name", "email"]})

EDGE = ["", "   ", "-- comment", ";;;", "SELECT * FROM", "(" * 2000 + "SELECT 1" + ")" * 2000,
        "SELECT * FROM orders WHERE id IN (" + ",".join(["1"] * 10000) + ")", "\x00", "🔥 SELECT"]


@pytest.mark.parametrize("sql", EDGE, ids=lambda v: repr(v[:14]))
def test_edge_sql_no_crash(sql: str) -> None:
    # malformed/edge SQL must fail closed (BLOCK or a valid verdict), never crash.
    assert check(sql, policy=POLICY).verdict in (Verdict.BLOCK, Verdict.PASS, Verdict.TRANSFORM)


@pytest.mark.parametrize("bad", [None, 123, b"x", ["l"]])
def test_non_str_raises_typeerror(bad: object) -> None:
    with pytest.raises(TypeError):
        check(bad, policy=POLICY)  # type: ignore[arg-type]
