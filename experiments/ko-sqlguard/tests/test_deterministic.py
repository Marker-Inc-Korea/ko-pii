"""Deterministic behavior: legitimate reads pass, policy knobs work, writes gated."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from ko_sqlguard import Guard, GuardPolicy, Severity, Verdict, check

ALLOW = GuardPolicy(allowed_tables={"orders": [], "customers": []}, default_limit=1000)


def test_simple_read_passes_or_transforms() -> None:
    r = check("SELECT id FROM orders WHERE id = 5", policy=ALLOW)
    assert r.ok
    assert r.verdict in (Verdict.PASS, Verdict.TRANSFORM)
    assert r.sql is not None


def test_select_constant_passes_without_limit() -> None:
    # No FROM => nothing to bound => no limit injection => clean PASS.
    r = check("SELECT 1", policy=GuardPolicy(allowed_tables=None))
    assert r.verdict is Verdict.PASS
    assert r.sql == "SELECT 1"


def test_join_with_condition_passes() -> None:
    sql = "SELECT o.id FROM orders o JOIN customers c ON o.cid = c.id WHERE o.id = 1"
    r = check(sql, policy=ALLOW)
    assert r.ok


def test_unlisted_table_blocks() -> None:
    r = check("SELECT * FROM secrets", policy=ALLOW)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "table_not_allowed" for v in r.violations)


def test_allowlist_none_allows_any_table() -> None:
    r = check("SELECT * FROM anything", policy=GuardPolicy(allowed_tables=None))
    assert r.ok


def test_public_schema_matches_bare_allow() -> None:
    r = check("SELECT * FROM public.orders", policy=ALLOW)
    assert r.ok


def test_cte_name_not_treated_as_table() -> None:
    sql = "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent"
    r = check(sql, policy=ALLOW)
    assert r.ok, [v.model_dump() for v in r.violations]


def test_cartesian_blocks_by_default() -> None:
    r = check("SELECT * FROM orders, customers", policy=ALLOW)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "cartesian" for v in r.violations)


def test_cartesian_allowed_when_disabled() -> None:
    p = GuardPolicy(allowed_tables={"orders": [], "customers": []}, block_cartesian=False)
    r = check("SELECT * FROM orders, customers WHERE orders.id = 1", policy=p)
    assert r.ok


# --- column allowlist ---


def test_column_allowlist_blocks_unlisted_column() -> None:
    p = GuardPolicy(allowed_tables={"orders": ["id", "status"]})
    r = check("SELECT id, secret_ssn FROM orders", policy=p)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "column_not_allowed" for v in r.violations)


def test_column_allowlist_allows_listed_columns() -> None:
    p = GuardPolicy(allowed_tables={"orders": ["id", "status"]}, default_limit=None)
    r = check("SELECT id, status FROM orders WHERE id = 1", policy=p)
    assert r.ok, [v.model_dump() for v in r.violations]


def test_star_blocked_under_column_restriction() -> None:
    p = GuardPolicy(allowed_tables={"orders": ["id"]})
    r = check("SELECT * FROM orders", policy=p)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "column_not_allowed" for v in r.violations)


# --- write mode ---


def test_read_only_policy_rejects_write_flags() -> None:
    import pytest

    with pytest.raises(ValueError):
        GuardPolicy(allow_update=True)  # read_only defaults True -> conflict


def test_write_mode_allows_update_with_where() -> None:
    p = GuardPolicy(read_only=False, allow_update=True, allowed_tables=None, default_limit=None)
    r = check("UPDATE orders SET total = 0 WHERE id = 1", policy=p)
    assert r.ok, [v.model_dump() for v in r.violations]


def test_write_mode_blocks_update_without_where() -> None:
    p = GuardPolicy(read_only=False, allow_update=True, allowed_tables=None)
    r = check("UPDATE orders SET total = 0", policy=p)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "missing_where" for v in r.violations)


def test_write_mode_still_blocks_unpermitted_delete() -> None:
    p = GuardPolicy(read_only=False, allow_update=True, allowed_tables=None)
    r = check("DELETE FROM orders WHERE id = 1", policy=p)
    assert r.verdict is Verdict.BLOCK


# --- severity threshold ---


def test_min_block_severity_downgrades_cartesian_to_warn() -> None:
    p = GuardPolicy(
        allowed_tables={"orders": [], "customers": []},
        min_block_severity=Severity.HIGH,
    )
    r = check("SELECT * FROM orders, customers", policy=p)
    # cartesian is MEDIUM < HIGH -> not blocking, recorded as a warn
    assert r.verdict is not Verdict.BLOCK
    assert any(v.code == "cartesian" for v in r.violations)


def test_critical_always_blocks_regardless_of_threshold() -> None:
    p = GuardPolicy(allowed_tables=None, min_block_severity=Severity.CRITICAL)
    r = check("DROP TABLE orders", policy=p)
    assert r.verdict is Verdict.BLOCK


def test_result_is_immutable() -> None:
    import pytest
    from pydantic import ValidationError

    r = check("SELECT 1", policy=GuardPolicy(allowed_tables=None))
    with pytest.raises((ValidationError, AttributeError, TypeError)):
        r.verdict = Verdict.BLOCK  # type: ignore[misc]


def test_guard_reusable_across_calls() -> None:
    g = Guard(ALLOW)
    assert g.check("SELECT id FROM orders WHERE id=1").ok
    assert not g.check("DROP TABLE orders").ok
    assert g.check("SELECT id FROM orders WHERE id=2").ok


def _tables(sql: str) -> set[str]:
    ast = sqlglot.parse_one(sql, read="postgres")
    ctes = {c.alias for c in ast.find_all(exp.CTE)}
    return {t.name for t in ast.find_all(exp.Table)} - ctes
