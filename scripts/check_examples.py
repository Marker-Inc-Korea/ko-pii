"""Execute README examples using the selected Python, never the source path."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(arguments: list[str], cwd: str) -> str:
    env = dict(os.environ, PYTHONPATH="", PYTHONUTF8="1")
    result = subprocess.run(
        [sys.executable, *arguments], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=60, check=True,
    )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-installed", action="store_true")
    args = parser.parse_args()
    example = (ROOT / "examples/quickstart.py").read_text(encoding="utf-8").strip()
    for name in ("README.md", "README.en.md"):
        readme = (ROOT / name).read_text(encoding="utf-8")
        if f"```python\n{example}\n```" not in readme:
            raise ValueError(f"{name}: quickstart differs from tested example")
    with tempfile.TemporaryDirectory(prefix="ko-pii-examples-") as work:
        location = run(["-c", "import ko_pii; print(ko_pii.__file__)"], work).strip()
        if args.require_installed and ROOT / "src" in Path(location).resolve().parents:
            raise ValueError("source tree imported instead of installed wheel")
        output = run([str(ROOT / "examples/quickstart.py")], work)
        assert "<EMAIL_1>" in output and "<PHONE_1>" in output
        for kind, name in (("text", "input.txt"), ("json", "request.json")):
            destination = Path(work) / f"result.{kind}"
            run(["-m", "ko_pii.cli", str(ROOT / "examples" / name),
                 "--format", kind, "--policy", str(ROOT / "examples/policy.json"),
                 "--output", str(destination)], work)
            value = destination.read_text(encoding="utf-8")
            assert "demo@example.com" not in value and "010-2345-6789" not in value
            if kind == "json":
                assert json.loads(value)["count"] == 2
    print("README Python, text CLI and structured CLI examples passed")


if __name__ == "__main__":
    main()
