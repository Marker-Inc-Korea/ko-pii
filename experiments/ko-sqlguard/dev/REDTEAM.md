# ko-sqlguard red-team report

This directory holds the diagnostic + adversarial tooling used while building
ko-sqlguard v1. It documents how the deterministic checks were validated against
the **actually installed** `sqlglot` (30.10.0) rather than assumed node names.

## Scripts

| File | Purpose |
|---|---|
| `probe_sqlglot.py` | Enumerate real AST node classes per statement type (caught `TruncateTable`, `Transaction`, the `Command` catch-all, `None`/`Semicolon` nodes in stacked parses). |
| `probe2.py` | Confirm write-via-read shapes: `SELECT INTO` (`into` arg), `FOR UPDATE` (`locks`), data-modifying CTEs, `COPY` → `exp.Copy`. |
| `probe3.py` | Verify the three structural-bug fixes: paren-wrapped `FOR UPDATE` (`exp.Lock`), `FETCH FIRST` (`exp.Fetch`), and `traverse_scope` table resolution. |
| `redteam_harness.py` | Feed candidate SQL (stdin, one per line) → print ko-sqlguard's verdict. Used by the workflow agents. |
| `redteam_workflow.js` | The 8-lens adversarial Workflow (attack → independent skeptic verify). |
| `reverify.py` | Re-run the workflow's "confirmed" escapes in one clean process (free of the agents' shared-temp-file race), reading base64 payloads to preserve exact bytes. |

Run the harness:

```bash
printf '%s\n' 'DROP TABLE x' '(SELECT * FROM orders) FOR UPDATE' | .venv/bin/python dev/redteam_harness.py
```

## What the red team found

An 8-lens multi-agent workflow (stacked queries, comment/case evasion,
CTE/subquery allowlist bypass, PG-specific features, dangerous functions,
identifier/quoting tricks, write-via-read, parser confusion) generated ~119
candidate escapes; each was independently verified, and 89 unique payloads were
re-confirmed in a single clean process. They clustered into **4 real bugs**, all
now fixed with regression tests in `tests/test_redteam_regression.py`:

1. **CRITICAL — CTE-alias scope bypass.**
   `SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)`
   read disallowed tables (incl. `pg_shadow` / `pg_authid` — password hashes).
   The old `cte_aliases()` collected CTE names statement-wide, so the inner CTE
   wrongly shadowed the *outer* `FROM secrets`. Fixed by resolving physical
   tables with `sqlglot.optimizer.scope.traverse_scope` (scope-aware), unioned
   with a fail-closed global fallback. One agent reproduced the read against a
   live PostgreSQL 16 (seq scan on the physical table).

2. **HIGH — locking reads behind a wrapper.**
   `(SELECT * FROM orders) FOR UPDATE` and all `FOR UPDATE/SHARE/NO KEY/...`
   variants escaped: the lock attaches to the outer `Subquery`, not the inner
   `Select`. Fixed by matching any `exp.Lock` node.

3. **HIGH — incomplete dangerous-function denylist.**
   `pg_file_write`, `lo_*`, `dblink_*`, `pg_promote`, `current_setting`,
   `setval`/`nextval`, advisory locks, `query_to_xmlschema`, server-file/WAL
   listings, etc. The default denylist was expanded ~5×. A denylist is inherently
   incomplete — this is the second line of defense behind a least-privilege role.

4. **MEDIUM — `FETCH FIRST n ROWS` not capped.**
   It is a `LIMIT` equivalent (parsed as `exp.Fetch`, not `exp.Limit`), so a
   huge `FETCH FIRST 1000000000` was uncapped. Now capped like `LIMIT`.

After the fixes: of the 89 payloads, **75 BLOCK and 1 is safely capped**.

## Rounds 2–4 (continued adversarial passes)

Each round re-ran the multi-agent attack → independent-verify loop against the
patched build; every confirmed escape became a regression test. The full
`tests/test_redteam_regression.py` (278+ cases) is the source of truth.

**Round 2 — table-alias column bypass.** `SELECT c.ssn FROM customers c` read a
disallowed column: the column allowlist keyed only the real table name, so a
one-token alias slipped past. Fixed by registering each table's alias against its
restricted column set. (`ALIAS_COLUMN_BYPASS`)

**Round 3 — alias bookkeeping regression + introspection functions.** The alias
fix had inflated the table count, breaking the *single-table* unqualified-column
judgement so `SELECT id FROM customers c` was wrongly blocked. Fixed by tracking
real tables (excluding aliases) separately; `count(*)`'s star was also exempted
from the column-star rule. Added `to_regclass`, `has_table_privilege`,
`schema_to_xml`, `currval`, `pg_get_viewdef`, `pg_export_snapshot`, … to the
denylist. (`ROUND3_*`)

**Round 4 — MERGE privilege escalation, derived-table alias, deeper denylist.**
1. **CRITICAL — MERGE per-action escalation.** `MERGE … WHEN MATCHED THEN DELETE`
   escaped under an `allow_update`-only policy: the DELETE action parses to
   `Var('DELETE')` (not `exp.Delete`), and a single mutation gate covered the
   whole statement. Now each `WHEN` action is gated by its own `allow_*` flag.
   A sibling false-positive (MERGE's `THEN UPDATE` is an `exp.Update`, which the
   missing-WHERE guard flagged) was fixed by exempting nodes inside a MERGE
   `WHEN` — the `ON` condition already scopes the rows.
2. **HIGH — derived-table alias column bypass.** `SELECT x.c FROM (SELECT ssn
   FROM customers) x(c)` re-exposed a disallowed column through a subquery
   alias. Outer columns are now resolved back to their real source column.
3. **HIGH — denylist gaps.** Added `pg_relation_filenode/size`,
   `pg_tablespace_location`, `pg_stat_reset_*`, `pg_stat_get_backend_*`,
   replication/WAL state (`pg_replication_slot_advance`, `pg_wal_replay_pause`,
   `pg_control_*`), object identity (`pg_describe_object`, `pg_identify_object`,
   `pg_get_object_address`, `pg_get_function_arguments`), `row_security_active`,
   and the `*_shared` advisory-lock variants.

## Out of scope by design (the remaining 13)

`generate_series(1, 1e18)`, `repeat('x', 2e9)`, `array_fill(...)`, and unbounded
`WITH RECURSIVE` are **resource-exhaustion** payloads. They read no disallowed
data, mutate nothing, and touch no files/network — they just compute a lot. A
parser cannot statically bound runtime cost (the argument may be a column).
The correct controls are the database's `statement_timeout` / `work_mem`, and
the deferred EXPLAIN cost guard (`ko_sqlguard/cost.py`). This limitation is stated
in the README.
