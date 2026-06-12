"""Adversarial harness: feed candidate SQL payloads, get ko-sqlguard's verdict.

Usage:
    echo "DROP TABLE x" | .venv/bin/python redteam_harness.py
    .venv/bin/python redteam_harness.py < payloads.txt
    .venv/bin/python redteam_harness.py --json < payloads.txt

Reads one SQL statement per line (blank lines and lines starting with '#'
are skipped). Prints, for each, the verdict and violations under a strict
read-only policy. An ESCAPE is any payload whose verdict is not BLOCK — those
are what an attacker would want. Exit code is 0 always; parse the output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_sqlguard import GuardPolicy, Verdict, check  # noqa: E402

# A representative production-style read-only policy with an allowlist.
POLICY = GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
    default_limit=1000,
    max_limit=10000,
)


def run(lines: list[str], as_json: bool) -> None:
    results = []
    escapes = 0
    for raw in lines:
        sql = raw.rstrip("\n")
        if not sql.strip() or sql.lstrip().startswith("#"):
            continue
        try:
            r = check(sql, policy=POLICY)
            verdict = r.verdict.value
            viols = [{"code": v.code, "sev": v.severity.name, "reason": v.reason} for v in r.violations]
            escaped = r.verdict is not Verdict.BLOCK
        except Exception as e:  # a crash is itself a finding (fail-open!)
            verdict = "EXCEPTION"
            viols = [{"code": "harness_exception", "sev": "?", "reason": f"{type(e).__name__}: {e}"}]
            escaped = True
        if escaped:
            escapes += 1
        results.append({"sql": sql, "verdict": verdict, "escaped": escaped, "violations": viols})

    if as_json:
        print(json.dumps({"escapes": escapes, "total": len(results), "results": results}, indent=2))
        return

    for item in results:
        flag = "  *** ESCAPE ***" if item["escaped"] else ""
        print(f"[{item['verdict'].upper():9s}]{flag} {item['sql']}")
        for v in item["violations"]:
            print(f"            ({v['sev']}) {v['code']}: {v['reason']}")
    print(f"\n{escapes}/{len(results)} payloads ESCAPED (verdict != BLOCK)")


if __name__ == "__main__":
    as_json = "--json" in sys.argv[1:]
    run(sys.stdin.read().splitlines(), as_json)
