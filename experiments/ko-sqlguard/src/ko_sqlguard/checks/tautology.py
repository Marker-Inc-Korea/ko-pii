"""Heuristic tautology detector for the ToxicSQL `OR 1=1` payload family.

Flags predicates that are constantly true: a bare TRUE, equality between two
identical literals (1=1, 'a'='a'), or an OR with a constant-true branch.
Scans WHERE / HAVING / QUALIFY and JOIN ON predicates.
"""
from __future__ import annotations

import operator

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation

_CMP = {
    exp.EQ: operator.eq, exp.NEQ: operator.ne,
    exp.GT: operator.gt, exp.GTE: operator.ge,
    exp.LT: operator.lt, exp.LTE: operator.le,
}


def _lit(node: exp.Expression) -> tuple[str, object] | None:
    """Paren 을 벗기고 리터럴/불리언이면 (kind, value) 로 정규화. 숫자는 float 로(1=1.0 동치)."""
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.Boolean):
        return ("b", bool(node.this))
    if isinstance(node, exp.Literal):
        if node.is_string:
            return ("s", node.this)
        try:
            return ("n", float(node.this))
        except ValueError:
            return ("s", node.this)
    return None


def _const_eval(node: exp.Expression | None) -> bool | None:
    """상수 술어의 진리값. 컬럼 등 판정 불가면 None — '1=1','2>1','(1)=(1)','OR 1',
    'NOT 1=2','1=1.0' 같은 상수-참 우회군을 일관되게 평가한다."""
    if node is None:
        return None
    if isinstance(node, exp.Paren):
        return _const_eval(node.this)
    if isinstance(node, exp.Not):
        v = _const_eval(node.this)
        return None if v is None else (not v)
    if isinstance(node, exp.Boolean):
        return bool(node.this)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return None
        try:
            return float(node.this) != 0  # bare truthy 리터럴(OR 1)
        except ValueError:
            return None
    if isinstance(node, exp.Or):
        a, b = _const_eval(node.this), _const_eval(node.expression)
        if a is True or b is True:
            return True
        if a is False and b is False:
            return False
        return None
    if isinstance(node, exp.And):
        a, b = _const_eval(node.this), _const_eval(node.expression)
        if a is False or b is False:
            return False
        if a is True and b is True:
            return True
        return None
    for cls, op in _CMP.items():
        if isinstance(node, cls):
            lv, rv = _lit(node.this), _lit(node.expression)
            if lv is None or rv is None:
                return None
            (lk, lval), (rk, rval) = lv, rv
            if lk != rk:  # 숫자 vs 문자 등 이종 비교 — EQ=거짓, NEQ=참, 그 외 판정 보류
                if cls is exp.EQ:
                    return False
                if cls is exp.NEQ:
                    return True
                return None
            try:
                return bool(op(lval, rval))  # type: ignore[arg-type]  # same kind → comparable
            except TypeError:
                return None
    return None


def _is_const_true(node: exp.Expression | None) -> bool:
    return _const_eval(node) is True


def _predicate_roots(stmt: exp.Expression) -> list[exp.Expression]:
    roots: list[exp.Expression] = []
    for node in stmt.find_all(exp.Where, exp.Having, exp.Qualify):
        if node.this is not None:
            roots.append(node.this)
    for join in stmt.find_all(exp.Join):
        # LATERAL 조인의 'ON true' 는 PostgreSQL 필수 관용구(상관은 서브쿼리 내부에
        # 있음)라 행 필터 무력화가 아니다 → tautology 검사 제외.
        if isinstance(join.this, exp.Lateral):
            continue
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
