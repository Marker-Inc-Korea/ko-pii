"""Detect unconstrained cartesian products at the top level of a read query.

An explicit CROSS JOIN is always flagged (it is a cartesian product by
definition). An implicit comma join is flagged only when nothing constrains it
- neither a JOIN ON/USING nor a cross-table predicate in WHERE - so legitimate
old-style joins (`FROM a, b WHERE a.id = b.id`) are not false-positived.
"""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation


def _top_selects(stmt: exp.Expression) -> list[exp.Select]:
    if isinstance(stmt, exp.Select):
        return [stmt]
    if isinstance(stmt, (exp.Union, exp.Intersect, exp.Except)):
        return [s for s in (stmt.this, stmt.expression) if isinstance(s, exp.Select)]
    if isinstance(stmt, exp.Subquery) and isinstance(stmt.this, exp.Select):
        return [stmt.this]
    return []


def _where_links_tables(select: exp.Select) -> bool:
    """True if WHERE references columns from >= 2 distinct table qualifiers."""
    where = select.args.get("where")
    if where is None:
        return False
    qualifiers = {c.table for c in where.find_all(exp.Column) if c.table}
    return len(qualifiers) >= 2


def check_cartesian(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    if not policy.block_cartesian:
        return []

    violations: list[Violation] = []
    for select in _top_selects(stmt):
        # Each join is a relation beyond the base FROM table; no joins => no
        # cartesian risk. (sqlglot stores FROM under the key "from_", so we key
        # off "joins" instead, which is unambiguous.)
        joins = select.args.get("joins") or []
        if not joins:
            continue

        where_linked = _where_links_tables(select)
        for join in joins:
            has_on = join.args.get("on") is not None
            has_using = join.args.get("using") is not None
            kind = (join.kind or "").upper()
            side = (join.side or "").upper()
            explicit_cross = kind == "CROSS"
            implicit_unconstrained = (
                not has_on and not has_using and not side and not kind and not where_linked
            )
            if explicit_cross or implicit_unconstrained:
                violations.append(
                    Violation(
                        code="cartesian",
                        severity=Severity.MEDIUM,
                        reason="join without ON/USING produces a cartesian product",
                        action="block",
                        fix="Add a join condition (ON/USING) or a cross-table WHERE predicate.",
                    )
                )
                break
    return violations
