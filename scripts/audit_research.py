"""Inventory legacy research honestly, including known non-executable sources."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "research/catalog.json"


def inventory() -> dict:
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "data"], cwd=ROOT,
    ).decode("utf-8").split("\0")
    entries = []
    for name in sorted(filter(None, paths)):
        path = ROOT / name
        payload = path.read_bytes()
        row = {"path": name, "bytes": len(payload),
               "sha256": hashlib.sha256(payload).hexdigest()}
        if path.suffix == ".py":
            try:
                ast.parse(payload, filename=name)
            except (SyntaxError, ValueError, UnicodeError) as error:
                row.update(status="blocked", reason=type(error).__name__,
                           line=getattr(error, "lineno", None))
            else:
                row.update(status="legacy-parseable",
                           reason="Syntax only; dependencies, paths and results not certified.")
        else:
            row.update(status="historical-data", reason="Not a current package evaluation.")
        if name.startswith("data/kdpii/"):
            row.update(source="https://zenodo.org/records/10968609",
                       license="CC-BY-4.0; see data/kdpii/README.md")
        elif name.startswith("data/klue_ner/"):
            row.update(source="https://github.com/KLUE-benchmark/KLUE",
                       license="Check upstream file-specific terms; not package MIT")
        elif "/aihub_" in name:
            row.update(source="AI Hub derivative; see historical fetch scripts",
                       license="Redistribution permission not established by this inventory")
        else:
            row.update(source="Historical repository artifact; inspect associated README/script",
                       license="No blanket data license inferred from package MIT")
        entries.append(row)
    return {"schema_version": 1, "scope": "git-tracked data/ files", "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true",
                        help="explicit initial inventory; refuses to overwrite")
    args = parser.parse_args()
    current = inventory()
    if args.record:
        with CATALOG.open("x", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    else:
        previous = json.loads(CATALOG.read_text(encoding="utf-8"))
        if previous != current:
            parser.exit(1, "research inventory changed; inspect and update the explicit baseline\n")
    blocked = [row for row in current["entries"] if row["status"] == "blocked"]
    for row in blocked:
        print(f"KNOWN BLOCKED {row['path']}:{row['line']} ({row['reason']})")
    print(f"Inventory matched: {len(current['entries'])} files; {len(blocked)} known blocked scripts")


if __name__ == "__main__":
    main()
