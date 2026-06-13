"""Table and column allowlist enforcement (operates on a normalized AST)."""
from __future__ import annotations

from sqlglot import exp

from ..policy import GuardPolicy
from ..result import Severity, Violation
from ._ast import cte_aliases, real_tables, table_key_candidates


def _match_table(table: exp.Table, allowed: dict[str, frozenset[str] | None]) -> str | None:
    """Return the matched allowlist key, or None if the table is not allowed."""
    for cand in table_key_candidates(table):
        if cand in allowed:
            return cand
    return None


def check_tables(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    allowed = policy.normalized_allowed
    if allowed is None:  # None => all tables permitted
        return []

    violations: list[Violation] = []
    seen: set[str] = set()
    for table in real_tables(stmt):
        label = (f"{table.db}." if table.db else "") + table.name
        if label in seen:
            continue
        seen.add(label)
        if _match_table(table, allowed) is None:
            violations.append(
                Violation(
                    code="table_not_allowed",
                    severity=Severity.HIGH,
                    reason=f"table {label!r} is not in the allowlist",
                    action="block",
                    fix="Add the table to GuardPolicy.allowed_tables, or query an allowed table.",
                )
            )
    return violations


def check_columns(stmt: exp.Expression, policy: GuardPolicy) -> list[Violation]:
    allowed = policy.normalized_allowed
    if allowed is None:
        return []
    # Only tables with a column restriction (non-None set) participate.
    restricted = {k: v for k, v in allowed.items() if v is not None}
    if not restricted:
        return []

    violations: list[Violation] = []
    ctes = cte_aliases(stmt)
    tables = [t for t in real_tables(stmt)]
    # Map a bare/qualified table name AND its alias to its restricted column set.
    # Registering the alias is critical: a qualified column uses the alias
    # (`c.ssn` from `customers c`), so keying only by the real name lets the
    # column allowlist be bypassed with a one-token alias.
    restricted_tables: dict[str, frozenset[str]] = {}
    real_cols: list[frozenset[str]] = []  # 실테이블 단위(별칭 제외) — single/ambiguous 판정용
    for t in tables:
        cols: frozenset[str] | None = None
        for cand in table_key_candidates(t):
            found = restricted.get(cand)
            if found is not None:
                cols = found
                break
        if cols is not None:
            restricted_tables[t.name] = cols
            if t.alias:
                restricted_tables[t.alias] = cols
            real_cols.append(cols)

    if not restricted_tables:
        return []

    # A star (`*` or `t.*`) under a column restriction can't be constrained.
    # count(*) 의 star 는 행 수 집계라 컬럼 노출이 아니므로 제외(과탐 방지).
    if any(not isinstance(s.parent, exp.Count) for s in stmt.find_all(exp.Star)):
        violations.append(
            Violation(
                code="column_not_allowed",
                severity=Severity.MEDIUM,
                reason="SELECT * cannot be constrained while a column allowlist is active",
                action="block",
                fix="List explicit columns instead of '*'.",
            )
        )

    # 별칭은 같은 실테이블을 가리키므로 실테이블 수로 판정(별칭 등록이 부풀린 len 무시).
    single_table = real_cols[0] if len(real_cols) == 1 else None

    for col in stmt.find_all(exp.Column):
        qualifier = col.table
        name = col.name
        if qualifier:
            if qualifier in ctes:
                continue
            allowed_cols = restricted_tables.get(qualifier)
            if allowed_cols is not None and name.lower() not in allowed_cols:
                violations.append(_col_violation(name, qualifier))
        else:
            # Unqualified: resolvable only if there is exactly one restricted table.
            if single_table is not None and name.lower() not in single_table:
                violations.append(_col_violation(name, None))
            elif single_table is None and len(real_cols) > 1:
                violations.append(
                    Violation(
                        code="column_not_allowed",
                        severity=Severity.MEDIUM,
                        reason=f"unqualified column {name!r} is ambiguous under a column allowlist",
                        action="block",
                        fix="Qualify the column with its table name.",
                    )
                )
    return violations


def _col_violation(name: str, qualifier: str | None) -> Violation:
    label = f"{qualifier}.{name}" if qualifier else name
    return Violation(
        code="column_not_allowed",
        severity=Severity.MEDIUM,
        reason=f"column {label!r} is not in the allowlist",
        action="block",
        fix="Select only allowlisted columns.",
    )
