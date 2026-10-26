"""Run the installed wheel's product tests using only assets in the sdist."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile


def extract_source(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        roots = set()
        for member in members:
            path = PurePosixPath(member.name)
            if (not path.parts or path.is_absolute() or ".." in path.parts
                    or "\\" in member.name or not (member.isfile() or member.isdir())):
                raise ValueError("source archive must contain only relative regular files/directories")
            roots.add(path.parts[0])
        if len(roots) != 1:
            raise ValueError("source archive must have exactly one root")
        # Fresh temporary directory; every member was checked, including links.
        archive.extractall(destination, members=members, **(
            {"filter": "data"} if sys.version_info >= (3, 12) else {}
        ))
    return destination / roots.pop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    archives = list(args.dist.glob("*.tar.gz"))
    if len(archives) != 1:
        parser.error("expected one source archive")
    with tempfile.TemporaryDirectory(prefix="ko-pii-sdist-check-") as temporary:
        root = extract_source(archives[0], Path(temporary))
        env = dict(os.environ, PYTHONPATH="", PYTHONUTF8="1")
        for command in (
            ["-m", "pytest", "--import-mode=importlib", "-o", "pythonpath=", "-q"],
            ["scripts/check_examples.py", "--require-installed"],
        ):
            subprocess.run([args.python, *command], cwd=root, env=env, check=True, timeout=600)
    print("Source-only product tests and installed-wheel examples passed")


if __name__ == "__main__":
    main()
