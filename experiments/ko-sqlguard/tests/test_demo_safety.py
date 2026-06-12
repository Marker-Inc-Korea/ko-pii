"""Safety regression: the web demo must never gain a path that executes SQL.

The Streamlit demo's only job is to display ko-sqlguard's verdict. It must not
import a DB driver, open a connection, or run a query — that would defeat the
"parse-only, never execute" guarantee the project is built on.
"""
from __future__ import annotations

from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "dev" / "streamlit_app.py"

# Tokens that would indicate the demo can reach a database or execute code.
FORBIDDEN = [
    "import psycopg",
    "import psycopg2",
    "import sqlalchemy",
    "import sqlite3",
    "check_cost",
    "explain_cost_guard",
    ".connect(",
    ".cursor(",
    ".execute(",
    "os.system",
    "subprocess",
    "eval(",
    "exec(",
]


def test_demo_has_no_sql_execution_path() -> None:
    src = DEMO.read_text()
    hits = [tok for tok in FORBIDDEN if tok in src]
    assert not hits, f"demo must not be able to execute SQL; found: {hits}"


def test_demo_only_calls_check() -> None:
    src = DEMO.read_text()
    # The only guard entry point the demo uses is the pure parse-only check().
    assert ".check(" in src
