# ruff: noqa: E501  (SQL 코퍼스 — 긴 쿼리 문자열 가독성 우선)
"""ko-sqlguard 평가 코퍼스 — 블루팀(정상 분석 쿼리) + 레드팀(공격/우회).

블루팀: BI/대시보드가 실제로 던지는 read-only 분석 쿼리. 모두 PASS/TRANSFORM(=허용)
이어야 한다 → 과탐(FPR) 측정. 레드팀: 금지 테이블/컬럼 읽기·쓰기·위험 함수·우회.
모두 BLOCK 이어야 한다 → 탐지(recall) 측정. 정책은 회귀 테스트와 동일.

주: unqualified 컬럼을 섞은 mixed-join 은 fail-closed 로 차단(by_design)이라 블루팀에
넣지 않는다. 정상 분석 쿼리는 컬럼을 qualify 한다.
"""
from __future__ import annotations

from ko_sqlguard import GuardPolicy

POLICY = GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
    default_limit=1000,
    max_limit=10000,
)

# 블루팀 — 정상 read-only 분석 쿼리(도메인별). 모두 not BLOCK 이어야 한다.
BENIGN: list[tuple[str, str]] = [
    ("simple", "SELECT id, name, email FROM customers WHERE id = 1"),
    ("simple", "SELECT * FROM orders"),
    ("simple", "SELECT id, name FROM customers ORDER BY name LIMIT 50"),
    ("projection", "SELECT c.id, c.name FROM customers c"),
    ("alias", "SELECT c.id AS cid, c.email AS mail FROM customers c"),
    ("join", "SELECT o.id, c.name FROM orders o JOIN customers c ON o.id = c.id"),
    ("join", "SELECT o.total, c.email FROM orders o JOIN customers c ON o.id = c.id WHERE o.id = 1"),
    ("join-using", "SELECT id FROM customers JOIN orders USING (id)"),
    ("self-join", "SELECT a.total FROM orders a JOIN orders b ON a.id = b.id"),
    ("aggregate", "SELECT count(*) FROM orders"),
    ("aggregate", "SELECT count(*) AS n, sum(o.total) AS s FROM orders o"),
    ("aggregate", "SELECT c.email, count(*) FROM customers c GROUP BY c.email HAVING count(*) > 1"),
    ("window", "SELECT o.id, rank() OVER (ORDER BY o.total DESC) FROM orders o"),
    ("window", "SELECT sum(o.total) OVER () FROM orders o JOIN customers c ON o.id = c.id"),
    ("distinct", "SELECT DISTINCT c.email FROM customers c"),
    ("cte", "WITH r AS (SELECT * FROM orders) SELECT * FROM r"),
    ("cte", "WITH t AS (SELECT id, name FROM customers) SELECT t.id, t.name FROM t"),
    ("subquery", "SELECT o.id FROM orders o WHERE o.id IN (SELECT id FROM customers)"),
    ("subquery", "SELECT c.name FROM customers c WHERE EXISTS (SELECT 1 FROM orders o WHERE o.id = c.id)"),
    ("derived", "SELECT x.total FROM (SELECT o.total FROM orders o) x"),
    ("lateral", "SELECT c.name, lo.total FROM customers c LEFT JOIN LATERAL "
                "(SELECT o.total FROM orders o WHERE o.id = c.id LIMIT 1) lo ON true"),
    ("lateral", "SELECT c.id, recent.total FROM customers c JOIN LATERAL "
                "(SELECT o.total FROM orders o WHERE o.id = c.id LIMIT 1) recent ON true"),
    ("case", "SELECT c.id, CASE WHEN c.id > 0 THEN c.name ELSE c.email END FROM customers c"),
    ("func", "SELECT generate_series(1, 100)"),
    ("func", "SELECT count(*)::int FROM orders"),
    ("cast", "SELECT o.id::text FROM orders o"),
    ("limit", "SELECT * FROM orders FETCH FIRST 50 ROWS ONLY"),
    ("orderby", "SELECT o.id FROM orders o ORDER BY o.total DESC NULLS LAST"),
    ("union", "SELECT id FROM customers WHERE id = 1 UNION SELECT id FROM customers WHERE id = 2"),
    ("coalesce", "SELECT COALESCE(c.name, c.email) FROM customers c"),
]

# 레드팀 — 모두 BLOCK 이어야 한다(범주별).
ATTACK: list[tuple[str, str]] = [
    ("ddl", "DROP TABLE customers"),
    ("ddl", "TRUNCATE TABLE orders"),
    ("write", "DELETE FROM orders"),
    ("write", "UPDATE customers SET email = 'x'"),
    ("write", "INSERT INTO orders (id) VALUES (1)"),
    ("table-not-allowed", "SELECT * FROM secrets"),
    ("table-not-allowed", "SELECT passwd FROM pg_shadow"),
    ("col-not-allowed", "SELECT c.ssn FROM customers c"),
    ("col-not-allowed", "SELECT password FROM customers"),
    ("cte-alias-collision", "WITH c AS (SELECT 1 AS id) SELECT c.ssn FROM customers c LIMIT 10"),
    ("whole-row", "SELECT to_jsonb(c) FROM customers c JOIN orders o ON c.id = o.id"),
    ("whole-row", "SELECT row_to_json(c) FROM customers c"),
    ("using-col", "SELECT id FROM customers c JOIN orders o USING (id) JOIN customers c2 USING (ssn)"),
    ("unqualified-join", "SELECT ssn FROM customers JOIN orders USING (id)"),
    ("locking", "(SELECT * FROM orders) FOR UPDATE"),
    ("select-into", "SELECT * INTO dump FROM orders"),
    ("merge", "MERGE INTO orders o USING customers c ON o.id=c.id WHEN MATCHED THEN DO NOTHING"),
    ("dangerous-func", "SELECT pg_read_file('/etc/passwd')"),
    ("dangerous-func", "SELECT pg_sleep(10)"),
    ("dangerous-func", "SELECT pg_notify('c', 'x')"),
    ("dangerous-func", "SELECT lo_get(1)"),
    ("dangerous-func", "SELECT dblink_connect('host=evil')"),
    ("reg-cast", "SELECT 'pg_authid'::regclass"),
    ("catalog-func", "SELECT k.word FROM orders o JOIN LATERAL pg_get_keywords() k ON k.word = o.id"),
    ("cte-scope", "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)"),
    ("stacked", "SELECT 1; DROP TABLE orders"),
    ("tautology", "SELECT * FROM orders WHERE 1=1 OR 1=1"),
    ("cartesian", "SELECT * FROM orders, customers"),
]
