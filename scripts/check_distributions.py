"""Check that archives include executable documentation but no research corpus."""
from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path, PurePosixPath


def check_source(names: list[str]) -> None:
    relative = {str(PurePosixPath(name).relative_to(PurePosixPath(name).parts[0]))
                for name in names}
    required = {
        "README.md", "README.en.md", "CONTRIBUTING.md", "SECURITY.md",
        "examples/quickstart.py", "examples/policy.json", "examples/input.txt",
        "examples/request.json", "scripts/check_examples.py",
        "scripts/release_bundle.py", ".github/workflows/checks.yml",
        "tests/contracts/fixtures/1.22.0.json",
    }
    if not required <= relative:
        raise ValueError("source archive is missing documentation/test assets")
    if any(name == "data" or name.startswith("data/") for name in relative):
        raise ValueError("source archive contains historical research data")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    wheels, sources = list(args.dist.glob("*.whl")), list(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("expected one wheel and one source archive")
    with tarfile.open(sources[0]) as archive:
        check_source(archive.getnames())
    with zipfile.ZipFile(wheels[0]) as wheel:
        if any(name.startswith(("data/", "research/", "scripts/", "tests/", "examples/"))
               for name in wheel.namelist()):
            parser.error("wheel contains repository-only assets")
    print("Distribution scope passed: examples in sdist; research corpus excluded")


if __name__ == "__main__":
    main()
