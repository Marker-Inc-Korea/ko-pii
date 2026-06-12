"""Runnable quickstart: how ko-sqlguard sits between an LLM and a database.

    python examples/quickstart.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_sqlguard import Guard, GuardBlocked, GuardPolicy  # noqa: E402

guard = Guard(
    GuardPolicy(
        allowed_tables={"orders": [], "customers": ["id", "name"]},
        default_limit=500,
    )
)

EXAMPLES = [
    "SELECT id, name FROM customers WHERE id = 42",      # TRANSFORM (LIMIT injected)
    "SELECT * FROM orders",                              # TRANSFORM (LIMIT injected)
    "SELECT * FROM orders LIMIT 999999",                 # TRANSFORM (LIMIT capped)
    "DROP TABLE orders",                                 # BLOCK
    "SELECT * FROM orders; DROP TABLE orders",           # BLOCK (stacked)
    "SELECT * FROM secrets",                             # BLOCK (allowlist)
    "SELECT email FROM customers",                       # BLOCK (column allowlist)
    "SELECT pg_sleep(10)",                               # BLOCK (dangerous fn)
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",  # BLOCK (write-via-CTE)
]


def main() -> None:
    for sql in EXAMPLES:
        result = guard.check(sql)
        print(f"\n{sql}")
        print(f"  -> {result.verdict.value.upper()}")
        if result.sql and result.sql != sql:
            print(f"     rewritten: {result.sql}")
        for v in result.violations:
            print(f"     [{v.severity.name}/{v.action}] {v.code}: {v.reason}")

    print("\n--- enforce() raises on a blocked query ---")
    try:
        guard.enforce("DELETE FROM orders")
    except GuardBlocked as e:
        print(f"  GuardBlocked: {e}")


if __name__ == "__main__":
    main()
