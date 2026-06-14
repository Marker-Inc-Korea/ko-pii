# ko-sqlguard adversarial validation

This directory holds the diagnostic + adversarial tooling used to harden
ko-sqlguard against bypasses, validated against the **actually installed**
`sqlglot` (30.10.0) rather than assumed node names. The guard is exercised by
repeated multi-agent adversarial sweeps (attack → independent skeptic verify →
fix → regression test); every confirmed escape becomes a case in
`tests/test_redteam_regression.py`.

## Scripts

| File | Purpose |
|---|---|
| `probe_sqlglot.py` | Enumerate real AST node classes per statement type (caught `TruncateTable`, `Transaction`, the `Command` catch-all, `None`/`Semicolon` nodes in stacked parses). |
| `probe2.py` | Confirm write-via-read shapes: `SELECT INTO` (`into` arg), `FOR UPDATE` (`locks`), data-modifying CTEs, `COPY` → `exp.Copy`. |
| `probe3.py` | Verify structural-bug fixes: paren-wrapped `FOR UPDATE` (`exp.Lock`), `FETCH FIRST` (`exp.Fetch`), and `traverse_scope` table resolution. |
| `redteam_harness.py` | Feed candidate SQL (stdin, one per line) → print ko-sqlguard's verdict. Used by the adversarial workflow agents. |
| `redteam_workflow.js` | The multi-lens adversarial Workflow (attack → independent skeptic verify). |
| `reverify.py` | Re-run confirmed escapes in one clean process (free of the agents' shared-temp-file race), reading base64 payloads to preserve exact bytes. |

Run the harness:

```bash
printf '%s\n' 'DROP TABLE x' '(SELECT * FROM orders) FOR UPDATE' | .venv/bin/python dev/redteam_harness.py
```

## Defenses hardened by adversarial testing

The deterministic checks now cover these bypass families, each with regression
coverage. A least-privilege DB role remains the primary line of defense; this
guard is defense-in-depth in front of it.

**Out-of-allowlist reads via scope tricks.** Data-modifying / aliased CTEs,
subquery / UNION scope confusion, and CTEs whose name collides with a restricted
table's name *or* alias. Physical tables are resolved scope-aware with
`sqlglot.optimizer.scope.traverse_scope`, unioned with a fail-closed global
fallback; the column check consults the restricted set *before* any CTE skip, so
a decoy CTE can't shadow a real `FROM customers c` to leak `c.ssn`. A live
PostgreSQL 16 reproduction confirmed the original leak read password hashes from
`pg_shadow` / `pg_authid`.

**Column-allowlist bypasses.** Table aliases (`c.ssn` from `customers c`),
quoted upper-case aliases (`"C"`), derived-table **and** LATERAL aliases
(resolved back to their real source column so `lo.total`→`orders.total` passes
while `lo.ssn`→`customers.ssn` blocks), whole-row references
(`to_jsonb(c)` / `array_agg(customers)` / `row_to_json` serialize every column),
JOIN `USING (ssn)` columns, and unqualified columns in a mixed
restricted/unrestricted join. The last is **fail-closed**: an ambiguous
unqualified column must be qualified (`o.total`), since the parser has no schema
to prove it belongs to the unrestricted table.

**Write-via-read.** `SELECT INTO`, locking reads (`FOR UPDATE` / `SHARE` and all
variants) hidden behind paren / subquery wrappers, `MERGE` (gated per-WHEN
action — `DELETE` parses to `Var('DELETE')`, not `exp.Delete` — and blocked
outright under `read_only` since it is write/lock-class), and
`INSERT ... ON CONFLICT DO UPDATE` (gated by `allow_update`).

**Dangerous functions & casts.** A denylist of ~170 server-side / file /
network / replication / WAL / catalog / signaling functions (`pg_read_file`,
`lo_*`, `dblink_*`, `pg_notify`, `pg_get_keywords`, `pg_config`, replication and
object-identity introspection, …) — inherently incomplete, so extend it per
environment — plus `::reg*` casts (`'pg_authid'::regclass`) that probe the
catalog exactly like the blocked `to_reg*()` functions.

**Limit evasion.** `FETCH FIRST n ROWS` is a `LIMIT` equivalent (`exp.Fetch`, not
`exp.Limit`) and is capped the same way.

**Idiom false-positive guards.** LATERAL correlated lookups (`... JOIN LATERAL
(...) ON true`, `CROSS JOIN LATERAL`) are not treated as tautologies or cartesian
products; `count(*)` is exempt from the column-star rule.

The same adversarial sweeps hardened the sibling tools in this repo — **ko-pii**
(unicode-folding evasions and recall-safe false-positive guards) and
**ko-prompt-guard** (obfuscation normalization, Korean injection patterns, and
domain false-positive guards) — each with its own regression suite.

## Out of scope by design

`generate_series(1, 1e18)`, `repeat('x', 2e9)`, `array_fill(...)`, and unbounded
`WITH RECURSIVE` are **resource-exhaustion** payloads. They read no disallowed
data, mutate nothing, and touch no files/network — they just compute a lot. A
parser cannot statically bound runtime cost (the argument may be a column).
The correct controls are the database's `statement_timeout` / `work_mem`, and
the deferred EXPLAIN cost guard (`ko_sqlguard/cost.py`). This limitation is
stated in the README.
