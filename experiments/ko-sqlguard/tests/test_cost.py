"""Tier-2 EXPLAIN cost guard.

Unit tests use a fake DB-API connection (no database needed) and pin the core
safety invariant: the guard issues EXPLAIN, never EXPLAIN ANALYZE. Integration
tests run against a real PostgreSQL when KO_SQLGUARD_TEST_DSN is set, else skip.
"""
from __future__ import annotations

import json
import os

import pytest

from ko_sqlguard import Guard, GuardPolicy, Verdict, explain_cost_guard


class FakeCursor:
    def __init__(self, row: object = None, raise_on_execute: Exception | None = None) -> None:
        self.row = row
        self.raise_on_execute = raise_on_execute
        self.executed: str | None = None
        self.closed = False

    def execute(self, sql: str) -> None:
        self.executed = sql
        if self.raise_on_execute is not None:
            raise self.raise_on_execute

    def fetchone(self) -> object:
        return self.row

    def close(self) -> None:
        self.closed = True


class FakeConn:
    def __init__(self, row: object = None, raise_on_execute: Exception | None = None) -> None:
        self.cur = FakeCursor(row, raise_on_execute)

    def cursor(self) -> FakeCursor:
        return self.cur


def plan_row(cost: float, rows: int) -> tuple[object]:
    return ([{"Plan": {"Node Type": "Seq Scan", "Total Cost": cost, "Plan Rows": rows}}],)


LIMITS = GuardPolicy(allowed_tables=None, cost_threshold=1_000_000.0, max_estimated_rows=10_000_000)


# --- no-op when no thresholds are set ---


def test_noop_without_thresholds_does_not_touch_db() -> None:
    conn = FakeConn()
    r = explain_cost_guard("SELECT 1", GuardPolicy(allowed_tables=None), conn)
    assert r.verdict is Verdict.PASS
    assert conn.cur.executed is None  # never ran EXPLAIN


# --- threshold logic ---


def test_high_cost_blocks() -> None:
    r = explain_cost_guard("SELECT 1", LIMITS, FakeConn(plan_row(2_000_000_000.0, 5)))
    assert r.verdict is Verdict.BLOCK
    assert r.violations[0].code == "cost_exceeded"


def test_high_rows_blocks() -> None:
    r = explain_cost_guard("SELECT 1", LIMITS, FakeConn(plan_row(10.0, 500_000_000)))
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "rows_exceeded" for v in r.violations)


def test_cheap_query_passes() -> None:
    r = explain_cost_guard("SELECT 1", LIMITS, FakeConn(plan_row(12.3, 10)))
    assert r.verdict is Verdict.PASS
    assert not r.violations


def test_only_cost_threshold_set() -> None:
    p = GuardPolicy(allowed_tables=None, cost_threshold=100.0)
    assert explain_cost_guard("x", p, FakeConn(plan_row(200.0, 10**9))).verdict is Verdict.BLOCK
    assert explain_cost_guard("x", p, FakeConn(plan_row(50.0, 10**9))).verdict is Verdict.PASS


# --- fail-closed on any EXPLAIN error ---


def test_explain_error_is_failclosed_block() -> None:
    conn = FakeConn(raise_on_execute=RuntimeError("connection reset"))
    r = explain_cost_guard("SELECT 1", LIMITS, conn)
    assert r.verdict is Verdict.BLOCK
    assert r.violations[0].code == "explain_failed"


def test_malformed_explain_output_is_failclosed() -> None:
    r = explain_cost_guard("SELECT 1", LIMITS, FakeConn(row=("not json at all",)))
    assert r.verdict is Verdict.BLOCK
    assert r.violations[0].code == "explain_failed"


# --- driver result shape tolerance (psycopg3 list vs psycopg2 string) ---


def test_accepts_json_string_result() -> None:
    raw = json.dumps([{"Plan": {"Total Cost": 5.0, "Plan Rows": 1}}])
    r = explain_cost_guard("SELECT 1", LIMITS, FakeConn(row=(raw,)))
    assert r.verdict is Verdict.PASS


# --- THE safety invariant: EXPLAIN, never EXPLAIN ANALYZE ---


def test_never_runs_analyze() -> None:
    conn = FakeConn(plan_row(10.0, 10))
    explain_cost_guard("SELECT * FROM orders", LIMITS, conn)
    sql = (conn.cur.executed or "").upper()
    assert sql.startswith("EXPLAIN")
    assert "ANALYZE FALSE" in sql
    assert "ANALYZE TRUE" not in sql
    assert "EXPLAIN ANALYZE" not in sql  # the cardinal sin: would execute the query


def test_guard_check_cost_delegates() -> None:
    g = Guard(LIMITS)
    r = g.check_cost("SELECT 1", FakeConn(plan_row(9_999_999_999.0, 1)))
    assert r.verdict is Verdict.BLOCK


# --- integration: real PostgreSQL (opt-in via env) ---

DSN = os.environ.get("KO_SQLGUARD_TEST_DSN")
integration = pytest.mark.skipif(not DSN, reason="set KO_SQLGUARD_TEST_DSN to run")


@pytest.fixture(scope="module")
def pg_conn():  # type: ignore[no-untyped-def]
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(DSN, autocommit=True)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS kg_orders CASCADE")
    cur.execute("CREATE TABLE kg_orders (id int primary key, data text)")
    cur.execute("INSERT INTO kg_orders SELECT g, md5(g::text) FROM generate_series(1,50000) g")
    cur.execute("ANALYZE kg_orders")
    cur.close()
    yield conn
    conn.close()


@integration
def test_integration_cartesian_blocks(pg_conn) -> None:  # type: ignore[no-untyped-def]
    p = GuardPolicy(allowed_tables=None, cost_threshold=1_000_000.0)
    r = explain_cost_guard("SELECT * FROM kg_orders a, kg_orders b", p, pg_conn)
    assert r.verdict is Verdict.BLOCK
    assert r.violations[0].code == "cost_exceeded"


@integration
def test_integration_generate_series_blocks(pg_conn) -> None:  # type: ignore[no-untyped-def]
    # The DoS the deterministic guard cannot catch — the planner estimates it here.
    p = GuardPolicy(allowed_tables=None, max_estimated_rows=10_000_000)
    r = explain_cost_guard("SELECT generate_series(1, 1000000000)", p, pg_conn)
    assert r.verdict is Verdict.BLOCK


@integration
def test_integration_normal_query_passes(pg_conn) -> None:  # type: ignore[no-untyped-def]
    p = GuardPolicy(allowed_tables=None, cost_threshold=1_000_000.0, max_estimated_rows=10_000_000)
    r = explain_cost_guard("SELECT * FROM kg_orders WHERE id = 1", p, pg_conn)
    assert r.verdict is Verdict.PASS
