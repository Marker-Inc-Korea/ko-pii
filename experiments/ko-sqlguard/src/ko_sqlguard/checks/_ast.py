"""AST helpers shared by checks. All identifier handling goes through
normalize_identifiers so quoted vs. unquoted casing follows PostgreSQL rules.
"""
from __future__ import annotations

from sqlglot import exp
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
from sqlglot.optimizer.scope import traverse_scope

# Node types that read data without mutating it. exp.Query covers Select and all
# set operations (Union/Intersect/Except) plus top-level Subquery; Values is a
# constant row source. Anything NOT in here is treated as non-read (fail-closed).
READ_NODE_TYPES: tuple[type, ...] = (exp.Query, exp.Values)

# Statement/command node types that mutate state or run server-side actions.
# Mapped to a policy attribute that, when True, permits them; None => never
# auto-permitted in v1 (always blocked).
DDL_PERMIT = "allow_ddl"
MUTATION_PERMIT: dict[type, str | None] = {
    exp.Insert: "allow_insert",
    exp.Update: "allow_update",
    exp.Delete: "allow_delete",
    exp.Merge: "allow_update",
    exp.Drop: DDL_PERMIT,
    exp.Create: DDL_PERMIT,
    exp.Alter: DDL_PERMIT,
    exp.TruncateTable: DDL_PERMIT,
    exp.Grant: DDL_PERMIT,
    # No permit flag in v1 -> always blocked.
    exp.Copy: None,
    exp.Command: None,
    exp.Transaction: None,
    exp.Commit: None,
    exp.Rollback: None,
    exp.Set: None,
}

# Human label + whether each mutation is DDL-grade (CRITICAL) vs DML-grade (HIGH).
DDL_NODES: frozenset[type] = frozenset(
    {exp.Drop, exp.Create, exp.Alter, exp.TruncateTable, exp.Grant, exp.Copy, exp.Command}
)


def normalized_copy(stmt: exp.Expression) -> exp.Expression:
    """Return a normalized copy: unquoted identifiers folded to lowercase,
    quoted identifiers preserved (PostgreSQL semantics)."""
    return normalize_identifiers(stmt.copy(), dialect="postgres")


def unwrap(stmt: exp.Expression) -> exp.Expression:
    """Peel a top-level parenthesized subquery to inspect the real statement."""
    seen = 0
    while isinstance(stmt, exp.Subquery) and stmt.this is not None and seen < 50:
        stmt = stmt.this
        seen += 1
    return stmt


def cte_aliases(stmt: exp.Expression) -> set[str]:
    return {c.alias for c in stmt.find_all(exp.CTE) if c.alias}


def _scope_physical_tables(stmt: exp.Expression) -> list[exp.Table]:
    """Tables that bind to a real source (not a CTE) per SQL scope rules.

    Uses sqlglot's scope resolver so a CTE named after a table only shadows
    that table within its own scope. Defends against the bypass
    `SELECT * FROM secrets WHERE id IN (WITH secrets AS (...) ...)`, where the
    inner CTE is NOT in scope for the outer `FROM secrets`.
    """
    nodes: list[exp.Table] = []
    seen: set[int] = set()
    for scope in traverse_scope(stmt):
        for source in scope.sources.values():
            if isinstance(source, exp.Table) and id(source) not in seen:
                seen.add(id(source))
                nodes.append(source)
    return nodes


def real_tables(stmt: exp.Expression) -> list[exp.Table]:
    """Physical tables referenced, resolved with scope awareness.

    Union of (a) scope-resolved physical sources and (b) a global fallback that
    excludes statement-wide CTE names. (a) catches inner CTEs that wrongly shadow
    an outer table; (b) covers writes / statements the scope resolver may not
    fully model. The union is fail-closed: a table slips through only if BOTH
    methods agree it is a CTE in every scope.
    """
    nodes: list[exp.Table] = []
    seen: set[int] = set()

    try:
        scoped = _scope_physical_tables(stmt)
    except Exception:
        scoped = []
    for t in scoped:
        if id(t) not in seen:
            seen.add(id(t))
            nodes.append(t)

    ctes = cte_aliases(stmt)
    for t in stmt.find_all(exp.Table):
        if (t.name not in ctes or t.db) and id(t) not in seen:
            seen.add(id(t))
            nodes.append(t)

    return nodes


def table_key_candidates(table: exp.Table) -> list[str]:
    """Allowlist keys that could match this (already-normalized) table reference.

    Casing is preserved from normalization, so a quoted "Orders" yields the
    candidate "Orders" and will NOT match a lowercase allowlist key 'orders'.
    """
    name = table.name
    db = table.db
    if db:
        if db.lower() == "public":
            return [f"{db}.{name}", f"public.{name}", name]
        return [f"{db}.{name}"]
    return [name]
