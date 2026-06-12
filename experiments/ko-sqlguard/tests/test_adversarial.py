"""Red-team corpus: every payload must be BLOCKED. TDD target — written first.

The guard's contract under these tests: for adversarial input it returns a
GuardResult with verdict == BLOCK and ok is False, and it NEVER raises while
checking (fail-closed, not fail-crash). enforce() must raise GuardBlocked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ko_sqlguard import Guard, GuardBlocked, GuardPolicy, Verdict, check

FIXTURE = Path(__file__).parent / "fixtures" / "redteam.sql"

# A representative read-only policy with a table allowlist. `secrets`, `customers`,
# and any schema-qualified / quoted variant outside the list must be rejected.
POLICY = GuardPolicy(allowed_tables={"orders": [], "customers": []}, default_limit=500)


def _load_corpus() -> list[str]:
    lines: list[str] = []
    for raw in FIXTURE.read_text().splitlines():
        s = raw.strip()
        if not s or s.startswith("--"):
            continue
        lines.append(s)
    return lines


CORPUS = _load_corpus()


def test_corpus_nonempty() -> None:
    assert len(CORPUS) >= 40, "red-team corpus should be substantial"


@pytest.mark.parametrize("sql", CORPUS, ids=lambda s: s[:48])
def test_every_payload_blocks(sql: str) -> None:
    result = check(sql, policy=POLICY)
    assert result.verdict is Verdict.BLOCK, f"expected BLOCK, got {result.verdict}: {sql!r}"
    assert result.ok is False
    assert result.sql is None
    assert result.violations, "a block must explain itself with >=1 violation"


@pytest.mark.parametrize("sql", CORPUS, ids=lambda s: s[:48])
def test_enforce_raises_on_payloads(sql: str) -> None:
    guard = Guard(POLICY)
    with pytest.raises(GuardBlocked):
        guard.enforce(sql)


@pytest.mark.parametrize("sql", CORPUS, ids=lambda s: s[:48])
def test_check_never_raises(sql: str) -> None:
    # Fail-closed means a parser hiccup is a BLOCK, never an exception.
    guard = Guard(POLICY)
    result = guard.check(sql)  # must not raise
    assert result is not None


# --- targeted assertions on specific attack classes (clearer failure messages) ---


@pytest.mark.parametrize(
    "sql",
    [
        "COMMIT; DROP SCHEMA public CASCADE;",
        "SELECT * FROM orders; DROP TABLE orders",
        "SELECT * FROM orders;/**/DROP TABLE orders",
        ";DROP TABLE orders",
    ],
)
def test_stacked_queries_block(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    codes = {v.code for v in r.violations}
    assert "multi_statement" in codes or "statement_type" in codes


@pytest.mark.parametrize("sql", ["drop table orders", "DrOp TaBlE orders", "DROP/**/TABLE orders"])
def test_case_and_comment_bypass_block(sql: str) -> None:
    assert check(sql, policy=POLICY).verdict is Verdict.BLOCK


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders WHERE id = 1 OR 1=1",
        "SELECT * FROM orders WHERE 1=1",
        "SELECT * FROM orders WHERE 'a'='a'",
    ],
)
def test_tautology_block(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "tautology" for v in r.violations)


@pytest.mark.parametrize("sql", ["SELECT pg_sleep(5)", "SELECT pg_read_file('/etc/passwd')"])
def test_dangerous_functions_block(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "blocked_function" for v in r.violations)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM (SELECT * FROM secrets) t",
        "SELECT * FROM orders UNION SELECT * FROM secrets",
        "WITH s AS (SELECT * FROM secrets) SELECT * FROM s",
        "SELECT * FROM other.orders",
        'SELECT * FROM "Secrets"',
    ],
)
def test_allowlist_bypass_block(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "table_not_allowed" for v in r.violations)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
        "SELECT * INTO newtbl FROM orders",
        "SELECT * FROM orders FOR UPDATE",
        "COPY orders TO PROGRAM 'curl evil'",
        "DO $$ BEGIN NULL; END $$",
    ],
)
def test_write_via_read_block(sql: str) -> None:
    assert check(sql, policy=POLICY).verdict is Verdict.BLOCK


def test_fuzz_broken_sql_fails_closed() -> None:
    # Garbage / partial input must never PASS; it should BLOCK (parse_error) and never raise.
    garbage = [
        "SELECT * FROM",
        "'; DROP TABLE--",
        "((((",
        "SELECT * FROM orders WHERE",
        "\x00\x01 not sql",
        "UPDATE",
        "????",
    ]
    for g in garbage:
        r = check(g, policy=POLICY)
        assert r.verdict is not Verdict.PASS, f"garbage must not PASS: {g!r}"
        assert r.verdict is Verdict.BLOCK
