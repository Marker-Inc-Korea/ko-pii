"""Empirically measure what the EXPLAIN cost guard catches on a real PostgreSQL.

Seeds a 1M-row table, then runs the red-team DoS payloads (plus normal and
genuinely-expensive queries) through explain_cost_guard and prints the planner's
estimate + verdict. Honest measurement, not a claim.

    python dev/cost_probe.py            # assumes container on 127.0.0.1:55433
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psycopg

from ko_sqlguard import GuardPolicy
from ko_sqlguard.cost import _explain, explain_cost_guard

DSN = "host=127.0.0.1 port=55433 user=postgres password=test dbname=testdb"


def connect_with_retry(tries: int = 30) -> psycopg.Connection:
    last: Exception | None = None
    for _ in range(tries):
        try:
            return psycopg.connect(DSN, autocommit=True)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1)
    raise SystemExit(f"could not connect: {last}")


def seed(conn: psycopg.Connection) -> None:
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS orders, customers, secrets CASCADE")
    cur.execute("CREATE TABLE orders (id int primary key, cid int, total numeric, data text)")
    cur.execute(
        "INSERT INTO orders SELECT g, g%10000, random()*100, md5(g::text) "
        "FROM generate_series(1,1000000) g"
    )
    cur.execute("CREATE TABLE customers (id int primary key, name text, email text)")
    cur.execute("INSERT INTO customers SELECT g, 'n'||g, 'e'||g FROM generate_series(1,10000) g")
    cur.execute("CREATE TABLE secrets (id int, secret text)")
    cur.execute("INSERT INTO secrets SELECT g, 'S'||g FROM generate_series(1,100) g")
    cur.execute("ANALYZE")
    cur.close()


# (label, sql). DoS payloads that escaped the deterministic guard, plus controls.
QUERIES = [
    ("normal-pk", "SELECT * FROM orders WHERE id = 1"),
    ("normal-count", "SELECT count(*) FROM orders"),
    ("normal-small", "SELECT id, name FROM customers WHERE id = 5"),
    ("fullscan", "SELECT * FROM orders"),
    ("big-sort", "SELECT * FROM orders ORDER BY data"),
    ("self-cartesian", "SELECT * FROM orders a, orders b"),
    ("triple-cartesian", "SELECT * FROM orders a, orders b, orders c"),
    ("gen_series_1e9", "SELECT generate_series(1, 1000000000)"),
    ("gen_series_1e12", "SELECT generate_series(1, 1000000000000)"),
    ("gen_series_max", "SELECT generate_series(1, 9223372036854775807)"),
    ("repeat_2e9", "SELECT repeat('x', 2000000000)"),
    ("array_fill_1e8", "SELECT array_fill(0, ARRAY[100000000])"),
    ("recursive", "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r) SELECT count(*) FROM r"),
    ("join-no-filter", "SELECT * FROM orders o JOIN customers c ON o.cid = c.id"),
]

# Tunable thresholds for the demo.
POLICY = GuardPolicy(allowed_tables=None, cost_threshold=1_000_000.0, max_estimated_rows=10_000_000)


def main() -> None:
    conn = connect_with_retry()
    print("connected; seeding 1M-row table (a few seconds)...")
    seed(conn)
    print(f"\npolicy: cost_threshold={POLICY.cost_threshold:,.0f} "
          f"max_estimated_rows={POLICY.max_estimated_rows:,}\n")
    print(f"{'label':18s} {'verdict':6s} {'est_cost':>16s} {'est_rows':>20s}  reason")
    print("-" * 100)
    caught = 0
    for label, sql in QUERIES:
        # Verdict is what the guard actually returns (EXPLAIN refusal => fail-closed BLOCK).
        r = explain_cost_guard(sql, POLICY, conn)
        verdict = r.verdict.value.upper()
        reason = r.violations[0].code if r.violations else ""
        # Best-effort raw estimate for display.
        try:
            plan = _explain(sql, conn)
            cost_s = f"{plan.get('Total Cost', 0.0):,.1f}"
            rows_s = f"{plan.get('Plan Rows', 0):,}"
        except Exception:  # noqa: BLE001
            cost_s, rows_s = "(EXPLAIN refused)", "-"
        if verdict == "BLOCK":
            caught += 1
        print(f"{label:18s} {verdict:6s} {cost_s:>16s} {rows_s:>20s}  {reason}")
    print("-" * 100)
    print(f"{caught}/{len(QUERIES)} queries BLOCKED by cost guard")
    conn.close()


if __name__ == "__main__":
    main()
