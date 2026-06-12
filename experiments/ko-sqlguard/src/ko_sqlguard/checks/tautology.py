"""Heuristic tautology detector for the ToxicSQL `OR 1=1` payload family.

Flags predicates that are constantly true: a bare TRUE, equality between two
identical literals (1=1, 'a'='a'), or an OR with a constant-true branch.
Scans WHERE / HAVING / QUALIFY and JOIN ON predicates.
"""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation


def _is_const_true(node: exp.Expression | None) -> bool:
    if node is None:
        return False
    if isinstance(node, exp.Paren):
        return _is_const_true(node.this)
    if isinstance(node, exp.Boolean):
        return bool(node.this) is True
    if isinstance(node, exp.EQ):
        left, right = node.this, node.expression
        if isinstance(left, exp.Literal) and isinstance(right, exp.Literal):
            return left.this == right.this and left.is_string == right.is_string
    if isinstance(node, exp.Or):
        return _is_const_true(node.this) or _is_const_true(node.expression)
    return False


def _predicate_roots(stmt: exp.Expression) -> list[exp.Expression]:
    roots: list[exp.Expression] = []
    for node in stmt.find_all(exp.Where, exp.Having, exp.Qualify):
        if node.this is not None:
            roots.append(node.this)
    for join in stmt.find_all(exp.Join):
        on = join.args.get("on")
        if on is not None:
            roots.append(on)
    return roots


def check_tautology(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    if not policy.block_tautology:
        return []

    violations: list[Violation] = []
    for root in _predicate_roots(stmt):
        # The whole predicate is constant-true, or any OR-branch within it is.
        hit = _is_const_true(root)
        if not hit:
            for or_node in root.find_all(exp.Or):
                if _is_const_true(or_node.this) or _is_const_true(or_node.expression):
                    hit = True
                    break
        if hit:
            violations.append(
                Violation(
                    code="tautology",
                    severity=Severity.MEDIUM,
                    reason="constant-true predicate (e.g. OR 1=1) defeats row filtering",
                    action="block",
                    fix="Remove the always-true condition.",
                )
            )
            break
    return violations
