import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import build_scope, traverse_scope

print("=== Bug2: FOR UPDATE on paren wrapper ===")
for sql in ["(SELECT * FROM orders) FOR UPDATE", "SELECT * FROM orders FOR UPDATE",
            "(((SELECT * FROM orders))) FOR UPDATE", "(WITH c AS (SELECT 1) SELECT * FROM orders) FOR UPDATE"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    print(f"\n{sql!r} top={type(ast).__name__}")
    print("  top.locks:", ast.args.get("locks"))
    for sel in ast.find_all(exp.Select):
        print("  inner Select locks:", sel.args.get("locks"))
    # any Lock node anywhere?
    print("  find_all Lock:", [type(n).__name__ for n in ast.find_all(exp.Lock)] if hasattr(exp, "Lock") else "no Lock cls")

print("\n=== Bug4: FETCH FIRST ===")
for sql in ["SELECT * FROM orders FETCH FIRST 1000000000 ROWS ONLY", "SELECT * FROM orders LIMIT 5"]:
    ast = sqlglot.parse_one(sql, read="postgres")
    print(f"\n{sql!r}")
    print("  limit arg:", repr(ast.args.get("limit")))
    print("  has Fetch?", bool(list(ast.find_all(exp.Fetch))) if hasattr(exp, "Fetch") else "no Fetch cls")
    for f in ast.find_all(exp.Fetch) if hasattr(exp, "Fetch") else []:
        print("    Fetch:", repr(f), "| count:", f.args.get("count"), "| expression:", f.args.get("expression"))

print("\n=== Bug1: scope-aware table resolution ===")
sql = "SELECT * FROM secrets WHERE id IN (WITH secrets AS (SELECT 1 id) SELECT id FROM secrets)"
ast = sqlglot.parse_one(sql, read="postgres")
print(sql)
print("global find_all Table:", [t.name for t in ast.find_all(exp.Table)])
print("global find_all CTE:", [c.alias for c in ast.find_all(exp.CTE)])
print("\n--- traverse_scope physical sources per scope ---")
try:
    for scope in traverse_scope(ast):
        print("scope:", type(scope.expression).__name__,
              "| sources:", {k: type(v).__name__ for k, v in scope.sources.items()})
        # physical tables in this scope = sources that are exp.Table
        phys = [v.name for v in scope.sources.values() if isinstance(v, exp.Table)]
        print("   physical tables in scope:", phys)
except Exception as e:
    print("traverse_scope error:", type(e).__name__, e)

print("\n--- build_scope root, collect all physical tables across scopes ---")
def physical_tables(ast):
    phys = []
    for scope in traverse_scope(ast):
        for name, src in scope.sources.items():
            if isinstance(src, exp.Table):
                phys.append((src.db, src.name))
    return phys
print("physical (db,name):", physical_tables(ast))

# legit shadow case
sql2 = "WITH secrets AS (SELECT 1 id) SELECT * FROM secrets"
ast2 = sqlglot.parse_one(sql2, read="postgres")
print("\nLEGIT:", sql2)
print("physical (db,name):", physical_tables(ast2))

# catalog read
sql3 = "SELECT passwd FROM pg_shadow WHERE usename IN (WITH pg_shadow AS (SELECT 1) SELECT 1 FROM pg_shadow)"
print("\n", sql3)
print("physical (db,name):", physical_tables(sqlglot.parse_one(sql3, read="postgres")))
