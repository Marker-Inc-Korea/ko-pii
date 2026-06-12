"""Tier-2: EXPLAIN-based cost guard.

Catches what a parser structurally cannot: queries that are *shaped* fine but
would be ruinously expensive to run (cartesian blow-ups, huge scans/sorts,
set-returning explosions). It asks PostgreSQL's planner for an estimate and
blocks above a threshold.

SAFETY — the whole point of ko-sqlguard is to NOT run untrusted SQL, so this is
careful:
  * It runs ``EXPLAIN`` and NEVER ``EXPLAIN ANALYZE`` — the planner estimates the
    plan but does NOT execute the query. ``ANALYZE false`` is set explicitly as a
    second belt.
  * It lives OUTSIDE ``Guard.check()``. The deterministic hot path stays pure
    (no DB, no network). Call this only AFTER ``check()`` passes, on SQL you have
    already proven is a single read statement.
  * It is fail-closed: any EXPLAIN/connection error is a BLOCK, never a silent
    pass.

ko-sqlguard declares no database driver dependency. ``connection`` is any DB-API
2.0 connection (psycopg, psycopg2, ...); you own its lifecycle, its read-only /
least-privilege role, and ideally a ``statement_timeout`` as defense in depth.
"""
from __future__ import annotations

import json
from typing import Any

from .policy import GuardPolicy
from .result import GuardResult, Severity, Verdict, Violation

# ANALYZE false is the load-bearing safety flag: the query is planned, not run.
_EXPLAIN_PREFIX = "EXPLAIN (FORMAT JSON, COSTS true, ANALYZE false, TIMING false, BUFFERS false)"


def _extract_plan(raw: Any) -> dict[str, Any]:
    """Pull the top-level Plan dict out of an EXPLAIN (FORMAT JSON) result cell.

    Drivers return this as a parsed list/dict (psycopg3) or a JSON string
    (psycopg2); accept both.
    """
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list):
        if not raw:
            raise ValueError("empty EXPLAIN output")
        raw = raw[0]
    if not isinstance(raw, dict) or "Plan" not in raw:
        raise ValueError("unexpected EXPLAIN JSON shape")
    plan = raw["Plan"]
    if not isinstance(plan, dict):
        raise ValueError("EXPLAIN Plan is not an object")
    return plan


def _explain(sql: str, connection: Any) -> dict[str, Any]:
    cur = connection.cursor()
    try:
        cur.execute(f"{_EXPLAIN_PREFIX} {sql}")
        row = cur.fetchone()
    finally:
        cur.close()
    if not row:
        raise ValueError("EXPLAIN returned no rows")
    return _extract_plan(row[0])


def explain_cost_guard(
    sql: str,
    policy: GuardPolicy,
    connection: Any,
) -> GuardResult:
    """Block ``sql`` if the planner's estimated cost or row count is too high.

    Returns a GuardResult: BLOCK with a ``cost_exceeded`` / ``rows_exceeded`` /
    ``explain_failed`` violation, or PASS. Pass ``sql`` that has already cleared
    ``Guard.check()``. Set ``policy.cost_threshold`` and/or
    ``policy.max_estimated_rows`` to enable the respective limit; with neither
    set this is a no-op PASS (nothing to enforce).
    """
    if policy.cost_threshold is None and policy.max_estimated_rows is None:
        return GuardResult(verdict=Verdict.PASS, sql=sql, original_sql=sql, violations=())

    try:
        plan = _explain(sql, connection)
    except Exception as exc:  # fail-closed: we could not prove it is cheap
        return GuardResult(
            verdict=Verdict.BLOCK,
            sql=None,
            original_sql=sql,
            violations=(
                Violation(
                    code="explain_failed",
                    severity=Severity.HIGH,
                    reason=f"could not obtain a cost estimate: {type(exc).__name__}: {exc}",
                    fix="Ensure the connection is healthy and the SQL is a single statement.",
                ),
            ),
        )

    total_cost = float(plan.get("Total Cost", 0.0))
    plan_rows = int(plan.get("Plan Rows", 0))
    violations: list[Violation] = []

    if policy.cost_threshold is not None and total_cost > policy.cost_threshold:
        violations.append(
            Violation(
                code="cost_exceeded",
                severity=Severity.HIGH,
                reason=(
                    f"estimated planner cost {total_cost:.1f} exceeds "
                    f"cost_threshold {policy.cost_threshold:.1f}"
                ),
                fix="Add filters/LIMIT, or raise cost_threshold if this query is expected.",
            )
        )

    if policy.max_estimated_rows is not None and plan_rows > policy.max_estimated_rows:
        violations.append(
            Violation(
                code="rows_exceeded",
                severity=Severity.HIGH,
                reason=(
                    f"estimated {plan_rows} rows exceeds "
                    f"max_estimated_rows {policy.max_estimated_rows}"
                ),
                fix="Narrow the query, or raise max_estimated_rows.",
            )
        )

    if violations:
        return GuardResult(
            verdict=Verdict.BLOCK, sql=None, original_sql=sql, violations=tuple(violations)
        )
    return GuardResult(verdict=Verdict.PASS, sql=sql, original_sql=sql, violations=())
