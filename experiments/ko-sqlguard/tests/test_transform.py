"""LIMIT injection / capping transforms, audit-trail preservation, property test."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from ko_sqlguard import GuardPolicy, Verdict, check

P = GuardPolicy(allowed_tables=None, default_limit=1000, max_limit=10000)


def _limit_value(sql: str) -> int | None:
    ast = sqlglot.parse_one(sql, read="postgres")
    lim = ast.args.get("limit")
    if lim is None:
        return None
    return int(lim.expression.this)


def test_unbounded_select_gets_limit_injected() -> None:
    r = check("SELECT * FROM orders", policy=P)
    assert r.verdict is Verdict.TRANSFORM
    assert r.sql is not None
    assert _limit_value(r.sql) == 1000
    assert any(v.code == "limit_injected" for v in r.violations)


def test_excessive_limit_is_capped() -> None:
    r = check("SELECT * FROM orders LIMIT 99999", policy=P)
    assert r.verdict is Verdict.TRANSFORM
    assert _limit_value(r.sql or "") == 10000
    assert any(v.code == "limit_capped" for v in r.violations)


def test_reasonable_limit_left_alone() -> None:
    r = check("SELECT * FROM orders LIMIT 50", policy=P)
    assert _limit_value(r.sql or "") == 50
    assert not any(v.code.startswith("limit") for v in r.violations)


def test_no_limit_injection_when_disabled() -> None:
    p = GuardPolicy(allowed_tables=None, default_limit=None, max_limit=None)
    r = check("SELECT * FROM orders", policy=p)
    assert r.verdict is Verdict.PASS
    assert r.sql == "SELECT * FROM orders"


def test_injected_limit_never_exceeds_max_limit() -> None:
    # Regression: default_limit > max_limit must still inject <= max_limit.
    p = GuardPolicy(allowed_tables=None, default_limit=10000, max_limit=10)
    r = check("SELECT * FROM orders", policy=p)
    assert r.verdict is Verdict.TRANSFORM
    assert _limit_value(r.sql or "") == 10


def test_original_sql_preserved_on_transform() -> None:
    original = "SELECT * FROM orders"
    r = check(original, policy=P)
    assert r.original_sql == original
    assert r.sql != original
    assert "LIMIT" in (r.sql or "").upper()


def test_transform_is_low_severity_only() -> None:
    r = check("SELECT * FROM orders", policy=P)
    limit_v = [v for v in r.violations if v.code == "limit_injected"][0]
    assert limit_v.action == "transform"


def test_limit_injected_on_union() -> None:
    r = check("SELECT * FROM orders UNION SELECT * FROM customers", policy=P)
    assert r.verdict is Verdict.TRANSFORM
    assert "LIMIT" in (r.sql or "").upper()


# --- property: anything that PASSes or TRANSFORMs must re-parse to one safe read ---

PROP_INPUTS = [
    "SELECT * FROM orders",
    "SELECT id, name FROM orders WHERE id = 5",
    "SELECT * FROM orders LIMIT 10",
    "SELECT count(*) FROM orders",
    "WITH r AS (SELECT * FROM orders) SELECT * FROM r",
    "SELECT * FROM orders ORDER BY id DESC",
    "SELECT 1",
    "SELECT * FROM orders o JOIN customers c ON o.cid = c.id",
]

PROP_POLICY = GuardPolicy(allowed_tables={"orders": [], "customers": []}, default_limit=1000)


def test_property_passed_queries_are_single_safe_reads() -> None:
    for sql in PROP_INPUTS:
        r = check(sql, policy=PROP_POLICY)
        if r.verdict is Verdict.BLOCK:
            continue
        assert r.sql is not None
        # 1) re-parses to exactly one statement
        stmts = [s for s in sqlglot.parse(r.sql, read="postgres") if s is not None]
        stmts = [s for s in stmts if not isinstance(s, exp.Semicolon)]
        assert len(stmts) == 1, f"{sql!r} -> {r.sql!r}"
        stmt = stmts[0]
        # 2) is a read shape, with no mutating nodes anywhere
        assert isinstance(stmt, (exp.Query, exp.Values)), f"{r.sql!r} top={type(stmt).__name__}"
        for bad in (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
                    exp.Alter, exp.TruncateTable, exp.Merge, exp.Copy, exp.Command):
            assert not list(stmt.find_all(bad)), f"{r.sql!r} contains {bad.__name__}"
        # 3) only allowed tables survive
        ctes = {c.alias for c in stmt.find_all(exp.CTE)}
        tables = {t.name for t in stmt.find_all(exp.Table)} - ctes
        assert tables <= {"orders", "customers"}, f"{r.sql!r} -> tables {tables}"
