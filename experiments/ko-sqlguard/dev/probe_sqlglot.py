"""Probe installed sqlglot version: verify AST node class names and parse shapes
that ko-sqlguard's deterministic checks will rely on."""
import sqlglot
from sqlglot import exp, parse

print("sqlglot version:", sqlglot.__version__)
print()

CASES = [
    # statement types
    ("SELECT 1", "select"),
    ("SELECT * FROM orders UNION SELECT * FROM customers", "union"),
    ("WITH t AS (SELECT 1) SELECT * FROM t", "cte select"),
    ("DROP TABLE orders", "drop"),
    ("DROP SCHEMA public CASCADE", "drop schema"),
    ("DELETE FROM orders", "delete no where"),
    ("DELETE FROM orders WHERE id = 1", "delete where"),
    ("UPDATE orders SET x = 1", "update no where"),
    ("INSERT INTO orders VALUES (1)", "insert"),
    ("ALTER TABLE orders ADD COLUMN x INT", "alter"),
    ("CREATE TABLE x (id INT)", "create"),
    ("TRUNCATE TABLE orders", "truncate"),
    ("TRUNCATE orders", "truncate bare"),
    ("COMMIT", "commit"),
    ("BEGIN", "begin"),
    ("ROLLBACK", "rollback"),
    ("GRANT SELECT ON orders TO bob", "grant"),
    ("VACUUM FULL", "vacuum"),
    ("COPY orders TO '/tmp/x'", "copy"),
    ("DO $$ BEGIN NULL; END $$", "do block"),
    ("SET search_path TO public", "set"),
    ("SHOW search_path", "show"),
    ("CALL myproc()", "call"),
    ("EXECUTE prep(1)", "execute"),
    ("PREPARE prep AS SELECT 1", "prepare"),
    ("MERGE INTO a USING b ON a.id=b.id WHEN MATCHED THEN UPDATE SET x=1", "merge"),
    ("EXPLAIN SELECT 1", "explain"),
    ("SELECT pg_sleep(5)", "pg_sleep"),
    ("SELECT * FROM pg_read_file('/etc/passwd')", "pg_read_file table fn"),
    ("VALUES (1), (2)", "values"),
    ("TABLE orders", "TABLE shorthand"),
]

for sql, label in CASES:
    try:
        stmts = parse(sql, read="postgres")
        types = [type(s).__name__ + (f"(kind={s.args.get('kind')})" if isinstance(s, (exp.Drop, exp.Create)) else "") for s in stmts]
        print(f"{label:28s} -> {types}")
    except Exception as e:
        print(f"{label:28s} -> PARSE ERROR: {type(e).__name__}: {e}")

print()
print("=== multi-statement / piggyback ===")
for sql in [
    "COMMIT; DROP SCHEMA public CASCADE;",
    "SELECT 1; DROP TABLE orders",
    "SELECT 1;/**/DROP TABLE orders",
    "SELECT 1;",  # trailing semicolon - is it 1 or 2 statements?
    "SELECT 1;;",
    ";SELECT 1",
]:
    try:
        stmts = parse(sql, read="postgres")
        print(repr(sql), "->", [type(s).__name__ if s is not None else None for s in stmts])
    except Exception as e:
        print(repr(sql), "-> PARSE ERROR:", type(e).__name__, e)

print()
print("=== identifier case / quoting ===")
for sql in ['SELECT * FROM Orders', 'SELECT * FROM "Orders"', 'SELECT * FROM public.orders', 'SELECT * FROM other.orders']:
    ast = sqlglot.parse_one(sql, read="postgres")
    t = list(ast.find_all(exp.Table))[0]
    print(repr(sql), "-> name:", repr(t.name), "db:", repr(t.db), "quoted:", t.this.quoted if isinstance(t.this, exp.Identifier) else "?")

print()
print("=== normalize_identifiers ===")
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
for sql in ['SELECT * FROM Orders', 'SELECT * FROM "Orders"']:
    ast = sqlglot.parse_one(sql, read="postgres")
    norm = normalize_identifiers(ast, dialect="postgres")
    t = list(norm.find_all(exp.Table))[0]
    print(repr(sql), "-> normalized name:", repr(t.name))

print()
print("=== CTE / subquery table discovery ===")
ast = sqlglot.parse_one("WITH safe AS (SELECT * FROM secrets) SELECT * FROM safe JOIN orders ON safe.id=orders.id", read="postgres")
print("all tables:", [t.name for t in ast.find_all(exp.Table)])
print("cte names:", [c.alias for c in ast.find_all(exp.CTE)])

ast2 = sqlglot.parse_one("SELECT * FROM (SELECT * FROM secrets) t", read="postgres")
print("subquery tables:", [t.name for t in ast2.find_all(exp.Table)])

print()
print("=== comma join / cartesian shape ===")
ast = sqlglot.parse_one("SELECT * FROM a, b", read="postgres")
print("FROM a, b ->", ast.args.get("from"), "| joins:", ast.args.get("joins"))
ast = sqlglot.parse_one("SELECT * FROM a CROSS JOIN b", read="postgres")
j = ast.args.get("joins")[0]
print("CROSS JOIN -> join.kind:", j.kind, "side:", j.side, "on:", j.args.get("on"))
ast = sqlglot.parse_one("SELECT * FROM a JOIN b ON a.id=b.id", read="postgres")
j = ast.args.get("joins")[0]
print("INNER JOIN ON -> kind:", j.kind, "on present:", j.args.get("on") is not None)
ast = sqlglot.parse_one("SELECT * FROM a JOIN b USING (id)", read="postgres")
j = ast.args.get("joins")[0]
print("JOIN USING -> using present:", j.args.get("using") is not None)

print()
print("=== limit shape / injection ===")
ast = sqlglot.parse_one("SELECT * FROM orders", read="postgres")
print("no limit ->", ast.args.get("limit"))
ast2 = ast.limit(1000)
print("after .limit(1000):", ast2.sql(dialect="postgres"))
ast3 = sqlglot.parse_one("SELECT * FROM orders LIMIT 50000", read="postgres")
lim = ast3.args.get("limit")
print("LIMIT 50000 -> limit node:", repr(lim), "| expression:", repr(lim.expression))
ast4 = sqlglot.parse_one("SELECT 1 UNION SELECT 2", read="postgres")
print("union limit arg:", ast4.args.get("limit"), "| union.limit(10):", ast4.limit(10).sql(dialect="postgres"))

print()
print("=== functions ===")
ast = sqlglot.parse_one("SELECT pg_sleep(5), now(), version()", read="postgres")
for f in ast.find_all(exp.Func):
    print(type(f).__name__, "| sql_name:", f.sql_name() if hasattr(f, "sql_name") else "?", "| name attr:", getattr(f, "name", "?"), "| this:", repr(f.args.get("this")) if isinstance(f, exp.Anonymous) else "")

print()
print("=== tautology shapes ===")
for sql in ["SELECT * FROM t WHERE id=1 OR 1=1", "SELECT * FROM t WHERE TRUE", "SELECT * FROM t WHERE 'a'='a'"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    w = ast.args.get("where")
    print(repr(sql), "->", repr(w.this))
