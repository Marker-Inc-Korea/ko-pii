"""Deterministic checks. Each is a pure function over a sqlglot AST + policy."""
from __future__ import annotations

from .allowlist import check_columns, check_tables
from .cartesian import check_cartesian
from .functions import check_functions
from .limit import apply_limit
from .statement_type import check_statement_type
from .tautology import check_tautology
from .where import check_require_where

__all__ = [
    "apply_limit",
    "check_cartesian",
    "check_columns",
    "check_functions",
    "check_require_where",
    "check_statement_type",
    "check_tables",
    "check_tautology",
]
