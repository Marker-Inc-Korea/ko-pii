"""Re-verify the workflow's 'confirmed' escapes myself, in one clean process,
free of the temp-file race that affected the parallel verify agents.

Reads base64-encoded payloads (one per line) so exact bytes — including
embedded newlines/null bytes — are preserved. Prints only the payloads that
genuinely escape (verdict != BLOCK) under the same policy the harness uses.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ko_sqlguard import GuardPolicy, Verdict, check  # noqa: E402

POLICY = GuardPolicy(
    allowed_tables={"orders": [], "customers": ["id", "name", "email"]},
    default_limit=1000,
    max_limit=10000,
)

payloads = []
for line in Path("/tmp/confirmed_payloads.b64").read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    payloads.append(base64.b64decode(line).decode("utf-8", errors="replace"))

real_escapes = []
blocks = 0
for sql in payloads:
    try:
        r = check(sql, policy=POLICY)
        v = r.verdict
    except Exception as e:  # noqa: BLE001
        real_escapes.append((sql, f"EXCEPTION:{type(e).__name__}", []))
        continue
    if v is Verdict.BLOCK:
        blocks += 1
        continue
    # TRANSFORM/PASS: only a *real* escape if it reads/writes something it shouldn't.
    # We surface all non-BLOCK here and triage by eye.
    codes = [vi.code for vi in r.violations]
    real_escapes.append((sql, v.value, codes))

print(f"re-tested {len(payloads)} unique payloads: {blocks} BLOCK, {len(real_escapes)} non-BLOCK\n")
for sql, verdict, codes in real_escapes:
    oneline = sql.replace("\n", "\\n")
    print(f"[{verdict.upper():9s}] {oneline[:110]}")
    if codes:
        print(f"            violations: {codes}")
