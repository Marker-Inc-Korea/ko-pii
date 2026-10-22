"""Validated transformation choices; no detector or threshold overrides."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json

from ko_pii.labels import ALL_LABELS

STRATEGIES = frozenset({"tokenize", "redact", "asterisk", "hashed", "partial", "fpe"})


def validate_strategies(default: str, overrides: Mapping[str, str] | None) -> dict[str, str]:
    if not isinstance(default, str) or default not in STRATEGIES:
        raise ValueError("Unknown strategy")
    if overrides is not None and not isinstance(overrides, Mapping):
        raise ValueError("strategies must map labels to substitution strategies")
    result = dict(overrides or {})
    if any(not isinstance(k, str) or k not in ALL_LABELS for k in result):
        raise ValueError("strategies contains an unknown category label")
    if any(not isinstance(v, str) or v not in STRATEGIES for v in result.values()):
        raise ValueError("strategies contains an unknown substitution strategy")
    return result


def policy_digest(mode: str, default: str, overrides: Mapping[str, str]) -> str:
    payload = {"version": 1, "mode": mode, "default": default, "strategies": dict(overrides)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
