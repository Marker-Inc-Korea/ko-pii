"""Block dangerous server-side functions (pg_sleep, pg_read_file, dblink, ...).

Matched on the function name in the AST, never on the raw SQL string, so
comments / casing / whitespace cannot smuggle a call past the check.
"""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation

# Casts to an OID-registry pseudo-type resolve a catalog object by name/OID —
# functionally identical to to_regclass()/to_regproc()/… which ARE on the denylist.
# `'pg_authid'::regclass` probes object existence with no table reference, so the
# table allowlist never engages. Block the cast form to match the function form.
_BLOCKED_CAST_TYPES: frozenset[str] = frozenset(
    {
        "regclass", "regproc", "regprocedure", "regoper", "regoperator",
        "regtype", "regrole", "regnamespace", "regconfig", "regdictionary",
        "regcollation",
    }
)


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
    for cast in stmt.find_all(exp.Cast):
        to = cast.args.get("to")
        tname = to.sql().lower() if to is not None else ""
        if tname in _BLOCKED_CAST_TYPES and "::regcast" not in flagged:
            flagged.add("::regcast")
            violations.append(
                Violation(
                    code="blocked_function",
                    severity=Severity.HIGH,
                    reason=f"cast to OID-registry type {tname!r} resolves catalog objects "
                    "(equivalent to the blocked to_reg*() functions)",
                    action="block",
                    fix=f"Remove the ::{tname} cast.",
                )
            )
    return violations
