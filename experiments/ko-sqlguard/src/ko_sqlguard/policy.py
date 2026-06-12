"""GuardPolicy: the single Pydantic model that configures every deterministic check.

Tier-2 seams (`pii_columns`, `cost_threshold`) are exposed here for API stability but
are NOT enforced in v1 — see cost.py / semantic.py.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .result import Severity

# Functions an LLM has no business calling in an analytics/read context. Matched on
# the AST function name (case-insensitive), never on the raw SQL string. This is a
# best-effort denylist of well-known dangerous built-ins: a denylist is inherently
# incomplete, so it is your SECOND line of defense behind a least-privilege DB role
# (a non-superuser cannot call most of these anyway). Extend via
# GuardPolicy.blocked_functions. Note: resource-exhaustion via ordinary functions
# (generate_series/repeat with huge args) is intentionally NOT covered here - bound
# that with the database's statement_timeout / work_mem, not a parser.
DEFAULT_BLOCKED_FUNCTIONS: frozenset[str] = frozenset(
    {
        # --- time-delay / DoS payloads ---
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        # --- filesystem access ---
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_ls_logdir",
        "pg_ls_waldir",
        "pg_ls_tmpdir",
        "pg_ls_archive_statusdir",
        "pg_logdir_ls",
        "pg_stat_file",
        "pg_file_write",
        "pg_file_unlink",
        "pg_file_rename",
        "pg_current_logfile",
        "pg_relation_filepath",
        "adminpack",
        # --- large objects (read/write server files & DB bytes) ---
        "lo_import",
        "lo_export",
        "lo_open",
        "lo_get",
        "lo_put",
        "lo_creat",
        "lo_create",
        "lo_unlink",
        "lo_from_bytea",
        "lo_truncate",
        "loread",
        "lowrite",
        # --- cross-server / network ---
        "dblink",
        "dblink_exec",
        "dblink_connect",
        "dblink_connect_u",
        "dblink_open",
        "dblink_fetch",
        "dblink_send_query",
        "dblink_get_result",
        "inet_server_addr",
        "inet_server_port",
        # --- admin / replication / backup / process control ---
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
        "pg_rotate_logfile",
        "pg_promote",
        "pg_switch_wal",
        "pg_switch_xlog",
        "pg_create_restore_point",
        "pg_drop_replication_slot",
        "pg_create_physical_replication_slot",
        "pg_create_logical_replication_slot",
        "pg_replication_origin_create",
        "pg_backup_start",
        "pg_backup_stop",
        "pg_start_backup",
        "pg_stop_backup",
        "pg_stat_reset",
        "pg_stat_get_activity",
        "pg_database_size",
        "pg_read_server_files",
        # --- configuration read/write (info disclosure / state change) ---
        "set_config",
        "current_setting",
        # --- sequence state mutation ---
        "setval",
        "nextval",
        # --- advisory locks (hold server resources) ---
        "pg_advisory_lock",
        "pg_advisory_lock_shared",
        "pg_advisory_xact_lock",
        "pg_advisory_xact_lock_shared",
        "pg_advisory_unlock",
        "pg_advisory_unlock_all",
        "pg_try_advisory_lock",
        "pg_try_advisory_xact_lock",
        # --- query-to-XML exfiltration (runs arbitrary SQL text) ---
        "query_to_xml",
        "query_to_xmlschema",
        "query_to_xml_and_xmlschema",
        "database_to_xml",
        "database_to_xmlschema",
        "table_to_xml",
        "cursor_to_xml",
    }
)


class GuardPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    read_only: bool = True
    allow_insert: bool = False
    allow_update: bool = False
    allow_delete: bool = False
    allow_ddl: bool = False

    # None = any table allowed. {"orders": []} = table allowed, all columns allowed.
    # {"orders": ["id", "status"]} = table allowed, only those columns allowed.
    # Keys may be bare ("orders") or schema-qualified ("public.orders").
    allowed_tables: dict[str, list[str]] | None = None

    require_where_on_write: bool = True
    default_limit: int | None = 1000
    max_limit: int | None = 10000
    block_cartesian: bool = True
    block_tautology: bool = True
    blocked_functions: frozenset[str] = DEFAULT_BLOCKED_FUNCTIONS

    # --- Tier-2: EXPLAIN cost guard (opt-in, used by ko_sqlguard.cost) ---
    # Enforced only when you call the cost guard with a DB connection; the
    # deterministic check() never reads these.
    cost_threshold: float | None = None  # block if planner Total Cost exceeds this
    max_estimated_rows: int | None = None  # block if planner Plan Rows exceeds this

    # --- Tier-2 seam: not enforced in v1 ---
    pii_columns: dict[str, list[str]] | None = None

    min_block_severity: Severity = Severity.MEDIUM

    @model_validator(mode="after")
    def _writes_require_not_read_only(self) -> GuardPolicy:
        if self.read_only and (
            self.allow_insert or self.allow_update or self.allow_delete or self.allow_ddl
        ):
            raise ValueError(
                "read_only=True conflicts with allow_insert/update/delete/ddl; "
                "set read_only=False explicitly to permit writes"
            )
        return self

    @model_validator(mode="after")
    def _limits_sane(self) -> GuardPolicy:
        for name in ("default_limit", "max_limit"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be >= 1 or None")
        return self

    normalized_allowed: dict[str, frozenset[str] | None] | None = Field(
        default=None, exclude=True, repr=False
    )

    @model_validator(mode="after")
    def _normalize_allowlist(self) -> GuardPolicy:
        """Pre-fold allowlist keys/columns to PostgreSQL's unquoted-identifier case."""
        if self.allowed_tables is None:
            object.__setattr__(self, "normalized_allowed", None)
            return self
        normalized: dict[str, frozenset[str] | None] = {}
        for table, columns in self.allowed_tables.items():
            key = table.strip().lower()
            normalized[key] = frozenset(c.strip().lower() for c in columns) if columns else None
        object.__setattr__(self, "normalized_allowed", normalized)
        return self
