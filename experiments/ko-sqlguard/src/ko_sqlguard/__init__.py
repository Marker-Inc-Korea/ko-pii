"""ko-sqlguard: deterministic, parse-only guardrails for LLM-generated PostgreSQL.

ko-sqlguard validates a SQL string BEFORE you execute it. It parses the query with
sqlglot and inspects the AST; it never runs the query against a database to
check it. It is one layer of defense-in-depth, not a substitute for least-
privilege database roles.

    from ko_sqlguard import Guard, GuardPolicy

    guard = Guard(GuardPolicy(allowed_tables={"orders": [], "customers": []}))
    safe_sql = guard.enforce(llm_generated_sql)  # raises GuardBlocked if unsafe
"""
from __future__ import annotations

from .cost import explain_cost_guard
from .guard import Guard, check
from .policy import GuardPolicy
from .result import (
    Action,
    GuardBlocked,
    GuardResult,
    Severity,
    Verdict,
    Violation,
)
from .semantic import SemanticReviewer

__version__ = "0.1.0"

__all__ = [
    "Action",
    "Guard",
    "GuardBlocked",
    "GuardPolicy",
    "GuardResult",
    "SemanticReviewer",
    "Severity",
    "Verdict",
    "Violation",
    "check",
    "explain_cost_guard",
    "__version__",
]
