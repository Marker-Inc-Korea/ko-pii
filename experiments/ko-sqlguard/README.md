# ko-sqlguard

**Deterministic, parse-only guardrails for LLM-generated PostgreSQL queries.**

> [!WARNING]
> **ko-sqlguard is one layer of defense-in-depth — not your only one.**
> It reduces the blast radius of a misbehaving LLM; it does not make running
> model-authored SQL "safe." Always **also** run the query through a database
> role with least privilege (read-only user, row-level security, `statement_timeout`,
> restricted `search_path`, no `COPY`/superuser). If ko-sqlguard is the only thing
> between an LLM and your data, you are one parser edge-case away from an incident.

---

## What it does

You have an LLM that writes SQL. Before that SQL touches your database, pass it
through ko-sqlguard:

```python
from ko_sqlguard import Guard, GuardPolicy, GuardBlocked

guard = Guard(GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name"]},
    default_limit=500,
))

try:
    safe_sql = guard.enforce(llm_generated_sql)   # rewritten if needed, e.g. LIMIT added
    rows = db.execute(safe_sql)
except GuardBlocked as blocked:
    # blocked.result.violations explains exactly why
    log.warning("blocked unsafe SQL: %s", blocked)
```

It parses the query with [`sqlglot`](https://github.com/tobymao/sqlglot) and makes
a decision from the **abstract syntax tree** — statement type, referenced tables
and columns, presence of a `WHERE` on writes, cartesian products, dangerous
functions, stacked statements. The result is one of:

| Verdict     | Meaning                                                        |
|-------------|----------------------------------------------------------------|
| `PASS`      | Query is allowed as-is.                                         |
| `TRANSFORM` | Query is allowed after a safe rewrite (e.g. an injected `LIMIT`). |
| `BLOCK`     | Query is rejected; `violations` say why.                       |

## The one differentiator: it parses, it does **not** execute

A common anti-pattern (e.g. naïve "is this valid SQL?" validators) is to check a
query by *running* it — `EXPLAIN`, or worse, the query itself — against the
database. That hands the very input you distrust to the engine you are trying to
protect.

**ko-sqlguard never connects to a database.** Its hot path (`Guard.check`) is a pure
function of `(sql, policy)`: no network, no DB driver, no LLM call. The only
dependencies are `sqlglot` and `pydantic`. Validation cannot have side effects
because there is nothing to have a side effect *on*.

## Why AST, not string matching

Blocklists like `if "drop" in sql.lower()` are trivially bypassed:

```
DrOp TaBlE orders          -- casing
DROP/**/TABLE orders        -- inline comment splits the keyword
"drop"                      -- a column literally named drop
```

ko-sqlguard decides on **node types** in the parse tree (`isinstance(node, exp.Drop)`),
so casing, comments, and whitespace are irrelevant — they all parse to the same
AST. And it is **fail-closed**: if `sqlglot` cannot parse the input, ko-sqlguard
cannot prove it is safe, so it `BLOCK`s.

## Deterministic checks in v1

| Check                        | What it blocks / does                                              | Severity        |
|------------------------------|-------------------------------------------------------------------|-----------------|
| Parse failure                | Anything unparseable → fail-closed block                          | CRITICAL        |
| Multiple statements          | `COMMIT; DROP …` stacked / piggyback queries                     | CRITICAL        |
| Statement type (read-only)   | DROP/DELETE/UPDATE/INSERT/ALTER/CREATE/TRUNCATE/COPY/DO/…         | CRITICAL / HIGH |
| Write-via-read               | Data-modifying CTEs, `SELECT … INTO`, `FOR UPDATE` locks         | CRITICAL / HIGH |
| Table allowlist              | Tables outside the allowlist (incl. via subquery/CTE/UNION)      | HIGH            |
| Column allowlist             | Columns outside the allowlist (and `SELECT *` under a restriction) | MEDIUM        |
| `WHERE` required on writes   | `UPDATE`/`DELETE` with no `WHERE` (mass mutation)                | CRITICAL        |
| Cartesian product            | Joins with no `ON`/`USING` / cross-table predicate               | MEDIUM          |
| Tautology                    | `OR 1=1`, `WHERE TRUE`, `'a'='a'`                                | MEDIUM          |
| Dangerous functions          | `pg_sleep`, `pg_read_file`, `dblink`, `lo_import`, …             | HIGH            |
| LIMIT enforcement            | Injects a default `LIMIT`; caps excessive ones (**transform**)   | LOW             |

`min_block_severity` tunes strictness: violations below the threshold are recorded
as warnings instead of blocking. `CRITICAL` always blocks.

## Policy

```python
GuardPolicy(
    read_only=True,                       # writes require read_only=False + an allow_* flag
    allow_insert=False, allow_update=False, allow_delete=False, allow_ddl=False,
    allowed_tables={"orders": [], "customers": ["id", "name"]},
    #   None        -> any table allowed
    #   {"t": []}   -> table t allowed, all columns
    #   {"t": [..]} -> table t allowed, only those columns
    #   keys may be bare ("orders") or schema-qualified ("public.orders")
    require_where_on_write=True,
    default_limit=1000,                   # injected on unbounded reads (None = off)
    max_limit=10000,                      # excess LIMITs capped to this (None = off)
    block_cartesian=True,
    block_tautology=True,
    min_block_severity=Severity.MEDIUM,
)
```

## API

```python
from ko_sqlguard import Guard, GuardPolicy, check

guard = Guard(policy)
result = guard.check(sql)     # -> GuardResult: .verdict .sql .original_sql .violations .ok
guard.enforce(sql)            # -> safe SQL string, or raises GuardBlocked

check(sql, policy=policy)     # module-level convenience, same as Guard(policy).check(sql)
```

`GuardResult` is immutable and preserves both `sql` (the possibly-rewritten query)
and `original_sql` (what the LLM produced) for auditing/logging.

## Install

```bash
pip install ko-sqlguard          # depends only on sqlglot + pydantic
```

## Scope and limits (read these)

- **PostgreSQL dialect only.** Parsing uses `read="postgres"`. Node names are
  pinned to the installed `sqlglot` (developed against **30.x**); a major sqlglot
  upgrade should be re-validated against the test suite.
- **Output guardrail only.** v1 validates the SQL the LLM emits. It does not
  inspect query *results* or the user's natural-language *intent*.
- **Allowlist casing.** Table/column matching folds unquoted identifiers to
  lowercase (PostgreSQL semantics). A case-sensitive quoted table like `"Orders"`
  is treated as distinct from `orders` and will not match a lowercase allowlist
  entry — by design, to avoid quoting-based bypass.
- **Not a SQL-injection fixer.** ko-sqlguard assumes you still use parameterized
  queries for user data. It guards the *shape* of an LLM-authored statement.
- **Runtime cost is the cost guard's job, not the parser's.** A parser cannot
  statically bound a query's runtime cost. The optional Tier-2 cost guard (below)
  asks the planner; a `statement_timeout` on the DB is still your backstop.
- **Dangerous-function denylist is best-effort.** `blocked_functions` covers the
  well-known file/large-object/dblink/admin/replication/settings built-ins, but a
  denylist can never be complete. Treat it as defense-in-depth behind a
  least-privilege role, and extend it for your environment.

## Tier-2: EXPLAIN cost guard (optional)

The deterministic `check()` cannot see runtime cost: `generate_series(1, 1e18)`
is a *shaped-fine* read. The cost guard closes that gap by asking PostgreSQL's
planner — **`EXPLAIN`, never `EXPLAIN ANALYZE`** (it estimates the plan, it does
**not** run the query; `ANALYZE false` is set explicitly). It lives *outside* the
pure hot path: call it only after `check()` passes, with your own DB connection.

```python
from ko_sqlguard import Guard, GuardPolicy

guard = Guard(GuardPolicy(
    allowed_tables=None,
    cost_threshold=1_000_000,       # block if planner Total Cost exceeds this
    max_estimated_rows=10_000_000,  # ...or if estimated row count does
))

result = guard.check(sql)                 # pure: parse-only, no DB
if result.ok:
    cost = guard.check_cost(result.sql, connection)  # Tier-2: EXPLAIN via your conn
    if not cost.ok:
        raise RuntimeError(cost.violations[0].reason)
```

ko-sqlguard declares **no DB driver dependency** — `connection` is any DB-API 2.0
connection you own (psycopg, psycopg2, …). It is fail-closed: any EXPLAIN error is
a BLOCK.

**Measured honestly** (1M-row table, `dev/cost_probe.py`): the cost guard catches
cartesian blow-ups, huge scans/sorts, and the `generate_series(1, 1e9…1e18)`
explosions the deterministic guard can't — the planner estimates those rows
exactly. It does **not** catch single-row memory bombs (`array_fill(0,
ARRAY[1e8])` → planner cost ≈ 0) or non-terminating `WITH RECURSIVE` (planner
can't estimate the recursion). For those, a DB `statement_timeout` remains the
final backstop. The cost guard is a strong second layer, not a complete one.

### Deliberately deferred to v2 (API seams exist, implementation does not)

`GuardPolicy.pii_columns` (PII column catalog) and `SemanticReviewer`
(`ko_sqlguard.semantic`, an LLM advisory protocol) are exposed for forward API
stability but are inert in v1. They live *outside* the deterministic hot path on
purpose: the parse-only guarantee depends on `check()` never making an I/O or
model call.

## License

MIT.
