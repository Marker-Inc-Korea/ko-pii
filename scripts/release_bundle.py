"""Bind a tested wheel and sdist to their source commit before publication."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def describe(root: Path, version: str, commit: str) -> dict:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("expected a stable three-part release version")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("expected a full Git commit ID")
    expected = {f"ko_pii-{version}-py3-none-any.whl", f"ko_pii-{version}.tar.gz"}
    folder = root / "dist"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("dist must be a real directory")
    paths = list(folder.iterdir())
    if {p.name for p in paths} != expected:
        raise ValueError("expected exactly the release wheel and source archive")
    files = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("distributions must be regular files")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        files[path.name] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
    return {"schema_version": 1, "version": version, "commit": commit, "files": files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "verify"])
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    try:
        actual = describe(args.root, args.version, args.commit)
        manifest = args.root / "distribution-manifest.json"
        if args.action == "seal":
            with manifest.open("x", encoding="utf-8") as stream:
                json.dump(actual, stream, indent=2, sort_keys=True)
                stream.write("\n")
        else:
            if manifest.is_symlink() or manifest.stat().st_size > 8192:
                raise ValueError("invalid distribution manifest")
            if json.loads(manifest.read_text(encoding="utf-8")) != actual:
                raise ValueError("tested distribution manifest does not match")
    except (OSError, ValueError) as error:
        parser.exit(1, f"release bundle: {error}\n")
    print(f"{args.action}: {args.version} ({args.commit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
