"""LIMIT enforcement (the one transforming check): inject a default LIMIT on
unbounded reads and cap excessive ones. Returns violations AND the possibly
rewritten statement."""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation


def _limit_literal_node(stmt: exp.Expression) -> exp.Literal | None:
    """The integer literal that bounds the row count, for either a LIMIT n or a
    FETCH FIRST n ROWS clause (both live under the `limit` arg in sqlglot)."""
    limit = stmt.args.get("limit")
    if limit is None:
        return None
    # LIMIT n -> Limit(expression=Literal); FETCH FIRST n ROWS -> Fetch(count=Literal)
    expr = limit.args.get("expression") or limit.args.get("count")
    if isinstance(expr, exp.Literal) and not expr.is_string:
        return expr
    return None


def _literal_limit(stmt: exp.Expression) -> int | None:
    node = _limit_literal_node(stmt)
    if node is None:
        return None
    try:
        return int(node.this)
    except (TypeError, ValueError):
        return None


def apply_limit(
    stmt: exp.Expression, policy: GuardPolicy
) -> tuple[exp.Expression, list[Violation]]:
    # Only bound queries that actually read rows from a source.
    if not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return stmt, []
    if stmt.find(exp.From) is None:
        return stmt, []
    if not hasattr(stmt, "limit"):
        return stmt, []

    has_limit = stmt.args.get("limit") is not None
    current = _literal_limit(stmt)

    if not has_limit:
        if policy.default_limit is None:
            return stmt, []
        # Never inject a bound above max_limit (default_limit may exceed it).
        inject = policy.default_limit
        if policy.max_limit is not None:
            inject = min(inject, policy.max_limit)
        new = stmt.limit(inject)
        return new, [
            Violation(
                code="limit_injected",
                severity=Severity.LOW,
                reason=f"unbounded read; injected LIMIT {inject}",
                action="transform",
                fix=None,
            )
        ]

    if policy.max_limit is not None and current is None:
        # 비리터럴 LIMIT(서브쿼리/파라미터/표현식)은 상한을 정적으로 보증할 수 없다 →
        # fail-closed 로 max_limit 을 강제 주입한다(무캡 통과 차단).
        new = stmt.limit(policy.max_limit)
        return new, [
            Violation(
                code="limit_capped",
                severity=Severity.LOW,
                reason=f"non-literal LIMIT cannot be bounded; forced to {policy.max_limit}",
                action="transform",
                fix=None,
            )
        ]

    if policy.max_limit is not None and current is not None and current > policy.max_limit:
        new = stmt.limit(policy.max_limit)
        return new, [
            Violation(
                code="limit_capped",
                severity=Severity.LOW,
                reason=f"LIMIT {current} exceeds max; capped to {policy.max_limit}",
                action="transform",
                fix=None,
            )
        ]

    return stmt, []
