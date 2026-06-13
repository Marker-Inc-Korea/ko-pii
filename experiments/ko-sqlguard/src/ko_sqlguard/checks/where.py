"""Require a WHERE clause on permitted UPDATE/DELETE (mass-mutation guard)."""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation


def _within_merge(node: exp.Expression) -> bool:
    """A MERGE WHEN action is scoped by the MERGE ON condition, not a WHERE."""
    p = node.parent
    while p is not None:
        if isinstance(p, (exp.When, exp.Merge)):
            return True
        p = p.parent
    return False


def check_require_where(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    if not policy.require_where_on_write:
        return []
    violations: list[Violation] = []
    for node_type in (exp.Update, exp.Delete):
        for node in stmt.find_all(node_type):
            if _within_merge(node):
                continue
            if node.args.get("where") is None:
                violations.append(
                    Violation(
                        code="missing_where",
                        severity=Severity.CRITICAL,
                        reason=f"{node_type.__name__.upper()} without WHERE affects every row",
                        action="block",
                        fix="Add a WHERE clause that scopes the rows to change.",
                    )
                )
    return violations
