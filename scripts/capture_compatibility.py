"""Capture a baseline only from the published 1.22.0 package, outside src."""
from __future__ import annotations

import argparse
from enum import Enum
import inspect
import json
from importlib.metadata import version
from pathlib import Path

import ko_pii
from ko_pii.reporting import explain


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if version("ko-pii") != "1.22.0" or ko_pii.__version__ != "1.22.0":
        raise ValueError("run with the published 1.22.0 environment")
    if root / "src" in Path(ko_pii.__file__).resolve().parents:
        raise ValueError("must capture installed package, not source")
    signatures = {}
    for name in ko_pii.__all__:
        target = getattr(ko_pii, name)
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError):
            continue
        signatures[name] = [
            {"name": p.name, "kind": p.kind.name,
             "required": p.default is inspect.Parameter.empty
             and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
            for p in signature.parameters.values()
        ]
    profile = ko_pii.PolicyProfile(
        {"mode": "STRICT", "strategy": "tokenize", "include": ["EMAIL"]},
        name="compatibility-fixture",
    )
    result = profile.process("demo@example.com")
    fixture = {
        "producer": {"package": "ko-pii", "version": version("ko-pii"),
                     "source": "https://pypi.org/project/ko-pii/1.22.0/",
                     "wheel_sha256": "0e5d2b5fc8227bf05b368a1a5b5b54aa66e3e1a229a2f81fed52c536b3f35385"},
        "exports": ko_pii.__all__, "signatures": signatures,
        "enums": {
            name: {key: member.value for key, member in getattr(ko_pii, name).__members__.items()}
            for name in ko_pii.__all__
            if isinstance(getattr(ko_pii, name), type) and issubclass(getattr(ko_pii, name), Enum)
        },
        "profile": profile.to_dict(), "profile_fingerprint": profile.fingerprint,
        "vault": result.vault.to_dict(), "explanation": explain(result),
    }
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(fixture, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
