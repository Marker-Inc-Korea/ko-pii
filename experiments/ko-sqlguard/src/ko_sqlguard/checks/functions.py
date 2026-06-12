"""Block dangerous server-side functions (pg_sleep, pg_read_file, dblink, ...).

Matched on the function name in the AST, never on the raw SQL string, so
comments / casing / whitespace cannot smuggle a call past the check.
"""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation


def _func_name(node: exp.Func) -> str | None:
    if isinstance(node, exp.Anonymous):
        name = node.name
        return name.lower() if name else None
    try:
        sql_name = node.sql_name()
    except Exception:
        return None
    return sql_name.lower() if sql_name else None


def check_functions(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    blocked = {f.lower() for f in policy.blocked_functions}
    if not blocked:
        return []

    violations: list[Violation] = []
    flagged: set[str] = set()
    for node in stmt.find_all(exp.Func):
        name = _func_name(node)
        if name and name in blocked and name not in flagged:
            flagged.add(name)
            violations.append(
                Violation(
                    code="blocked_function",
                    severity=Severity.HIGH,
                    reason=f"function {name}() is blocked (server-side / delay / file access)",
                    action="block",
                    fix=f"Remove the call to {name}().",
                )
            )
    return violations
