"""Guard: the deterministic, parse-only entry point.

check() is a pure function: parse the SQL once with sqlglot's postgres dialect,
run every deterministic check over the AST, and return a GuardResult. It never
touches a database, an LLM, or the network. Parsing failure is a BLOCK, not an
exception (fail-closed).
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

from . import checks
from .checks._ast import normalized_copy
from .policy import GuardPolicy
from .result import GuardBlocked, GuardResult, Severity, Verdict, Violation

_DIALECT = "postgres"


def _block(original: str, *violations: Violation) -> GuardResult:
    return GuardResult(
        verdict=Verdict.BLOCK,
        sql=None,
        original_sql=original,
        violations=tuple(violations),
    )


def _real_statements(parsed: Iterable[Any]) -> list[exp.Expression]:
    return [s for s in parsed if s is not None and not isinstance(s, exp.Semicolon)]


class Guard:
    """Reusable guard bound to a policy. Stateless across check() calls."""

    def __init__(self, policy: GuardPolicy | None = None) -> None:
        self.policy = policy or GuardPolicy()

    def check(self, sql: str) -> GuardResult:
        policy = self.policy
        original = sql

        if not sql or not sql.strip():
            return _block(
                original,
                Violation(
                    code="empty",
                    severity=Severity.CRITICAL,
                    reason="empty input is not a valid statement",
                ),
            )

        # 1) Parse once. Any failure is a hard block (we cannot prove safety).
        try:
            parsed = sqlglot.parse(sql, read=_DIALECT)
        except (ParseError, TokenError) as exc:
            return _block(
                original,
                Violation(
                    code="parse_error",
                    severity=Severity.CRITICAL,
                    reason=f"could not parse SQL: {type(exc).__name__}",
                    fix="Send a single, well-formed PostgreSQL statement.",
                ),
            )
        except Exception as exc:  # defensive: never crash the hot path
            return _block(
                original,
                Violation(
                    code="parse_error",
                    severity=Severity.CRITICAL,
                    reason=f"unexpected parser error: {type(exc).__name__}",
                ),
            )

        statements = _real_statements(parsed)
        if len(statements) == 0:
            return _block(
                original,
                Violation(
                    code="parse_error",
                    severity=Severity.CRITICAL,
                    reason="no executable statement found",
                ),
            )
        if len(statements) > 1:
            return _block(
                original,
                Violation(
                    code="multi_statement",
                    severity=Severity.CRITICAL,
                    reason=f"{len(statements)} statements found; only one is allowed "
                    "(stacked-query / piggyback defense)",
                    fix="Submit exactly one statement.",
                ),
            )

        # 2) Work on a normalized copy so identifier casing follows PG rules and
        #    transforms don't mutate the caller's AST.
        try:
            working = normalized_copy(statements[0])
        except Exception:
            working = statements[0].copy()

        violations: list[Violation] = []
        violations += checks.check_statement_type(working, policy)
        violations += checks.check_functions(working, policy)
        violations += checks.check_tables(working, policy)
        violations += checks.check_columns(working, policy)
        violations += checks.check_require_where(working, policy)
        violations += checks.check_cartesian(working, policy)
        violations += checks.check_tautology(working, policy)

        blocking = [
            v
            for v in violations
            if v.action == "block" and v.severity >= policy.min_block_severity
        ]
        if blocking:
            # Re-tag downgraded block-violations as warns for an honest result.
            return GuardResult(
                verdict=Verdict.BLOCK,
                sql=None,
                original_sql=original,
                violations=tuple(violations),
            )

        # 3) No block: apply the transforming LIMIT check and render.
        transformed, limit_violations = checks.apply_limit(working, policy)
        violations += limit_violations
        did_transform = bool(limit_violations)

        if did_transform:
            try:
                rendered = transformed.sql(dialect=_DIALECT)
            except Exception:
                rendered = original
            return GuardResult(
                verdict=Verdict.TRANSFORM,
                sql=rendered,
                original_sql=original,
                violations=tuple(violations),
            )

        return GuardResult(
            verdict=Verdict.PASS,
            sql=original,
            original_sql=original,
            violations=tuple(violations),
        )

    def enforce(self, sql: str) -> str:
        """Return safe SQL (rewritten if transformed) or raise GuardBlocked."""
        result = self.check(sql)
        if result.verdict is Verdict.BLOCK or result.sql is None:
            raise GuardBlocked(result)
        return result.sql

    def check_cost(self, sql: str, connection: object) -> GuardResult:
        """Tier-2 EXPLAIN cost guard. NOT part of the pure hot path — it talks to
        a database via ``connection`` (any DB-API 2.0 connection). Call this only
        on SQL that already passed ``check()``. See ``ko_sqlguard.cost``."""
        from .cost import explain_cost_guard

        return explain_cost_guard(sql, self.policy, connection)


def check(sql: str, policy: GuardPolicy | None = None) -> GuardResult:
    """Module-level convenience wrapper around Guard(policy).check(sql)."""
    return Guard(policy).check(sql)
