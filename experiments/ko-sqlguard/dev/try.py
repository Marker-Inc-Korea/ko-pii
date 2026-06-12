"""즉석 체험기: SQL을 주면 ko-sqlguard가 어떻게 판정하는지 색으로 보여준다.

    python dev/try.py "DROP TABLE orders"      # 한 건 판정
    python dev/try.py                          # 데모 모음 출력
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_sqlguard import Guard, GuardPolicy, Verdict

GUARD = Guard(
    GuardPolicy(
        allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
        default_limit=1000,
        max_limit=10000,
    )
)

RESET, RED, YELLOW, GREEN, DIM = "\033[0m", "\033[91m", "\033[93m", "\033[92m", "\033[2m"
COLOR = {Verdict.BLOCK: RED, Verdict.TRANSFORM: YELLOW, Verdict.PASS: GREEN}

DEMO = [
    "SELECT id, name FROM customers WHERE id = 42",
    "SELECT 이름, 나이 FROM 고객",                       # 한글 식별자 (allowlist 밖)
    "SELECT * FROM orders",
    "SELECT * FROM orders LIMIT 99999",
    "DROP TABLE orders",
    "SELECT * FROM orders; DROP TABLE orders",
    "SELECT * FROM secrets",
    "SELECT email FROM customers",
    "(SELECT * FROM orders) FOR UPDATE",
    "SELECT pg_sleep(10)",
    "SELECT pg_file_write('/tmp/x','data',false)",
    "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
]


def show(sql: str) -> None:
    r = GUARD.check(sql)
    c = COLOR[r.verdict]
    print(f"\n{c}● {r.verdict.value.upper():9s}{RESET} {sql}")
    if r.sql and r.sql != sql:
        print(f"  {DIM}↳ 재작성: {r.sql}{RESET}")
    for v in r.violations:
        if v.code == "limit_injected":
            continue
        print(f"  {c}└ [{v.severity.name}] {v.code}{RESET}: {v.reason}")


def main() -> None:
    args = sys.argv[1:]
    if args:
        show(" ".join(args))
        print()
        return
    policy = GUARD.policy
    print(f"{DIM}정책: 허용 테이블 = {list((policy.allowed_tables or {}).keys())} "
          f"| 기본 LIMIT {policy.default_limit} | 읽기전용{RESET}")
    for sql in DEMO:
        show(sql)
    print()


if __name__ == "__main__":
    main()
