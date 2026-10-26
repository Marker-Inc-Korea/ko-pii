"""Portable, local-only processing settings. No executable plugins or secrets."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from ko_pii.anonymizer import Anonymizer, AnonymizationResult
from ko_pii.core.modes import ProcessingMode
from ko_pii.field_rules import EACH, rules_from_json
from ko_pii.labels import validate_label_filter
from ko_pii.patterns.person import normalize_exclusions
from ko_pii.policy import validate_strategies
from ko_pii.structured import (
    StructuredLimits, StructuredResult, _field_exclusions, _labels,
    anonymize_json, anonymize_jsonl, loads_json,
)
from ko_pii.vault.reversible import ReversibleVault

CORE_OPTIONS = {"mode", "strategy", "strategies", "include", "exclude", "person_exclusions"}
FIELD_OPTIONS = {"field_labels", "field_rules", "field_person_exclusions"}


def _unwrap(value: Mapping[str, Any] | PolicyProfile) -> Mapping[str, Any]:
    if isinstance(value, PolicyProfile):
        return value.settings
    if not isinstance(value, Mapping):
        raise ValueError("policy requires an object")
    if "schema_version" in value or "settings" in value:
        if (not {"schema_version", "settings"} <= value.keys()
                or not value.keys() <= {"schema_version", "name", "settings"}
                or type(value["schema_version"]) is not int or value["schema_version"] != 1
                or not isinstance(value["settings"], Mapping)):
            raise ValueError("unsupported policy profile schema")
        _name(value.get("name", ""))
        return value["settings"]
    return value


def _name(value: Any) -> str:
    if (not isinstance(value, str) or len(value) > 80
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError("profile name must be a short display string")
    return value


def core_settings(value: Mapping[str, Any] | PolicyProfile) -> dict[str, Any]:
    try:
        value = _unwrap(value)
        if not value.keys() <= CORE_OPTIONS:
            raise ValueError
        mode = ProcessingMode(value.get("mode", "STRICT"))
        strategy = value.get("strategy", "tokenize")
        strategies = validate_strategies(strategy, value.get("strategies"))
        include = validate_label_filter(value.get("include"), name="include")
        exclude = validate_label_filter(value.get("exclude"), name="exclude")
        return {"mode": mode.value, "strategy": strategy, "strategies": strategies,
                "include": sorted(include) if include is not None else None,
                "exclude": sorted(exclude) if exclude else [],
                "person_exclusions": sorted(normalize_exclusions(value.get("person_exclusions")))}
    except (TypeError, ValueError):
        raise ValueError("invalid core policy; Vaults, model adapters and arbitrary options are not supported") from None


def structured_settings(value: Mapping[str, Any] | PolicyProfile) -> dict[str, Any]:
    try:
        value = _unwrap(value)
        if not value.keys() <= CORE_OPTIONS | FIELD_OPTIONS:
            raise ValueError
        core = core_settings({k: v for k, v in value.items() if k in CORE_OPTIONS})
        anon = Anonymizer(**{**core, "mode": ProcessingMode(core["mode"])})
        labels = _labels(value.get("field_labels"), anon)
        if len(labels) > 128 or any(len(path) > 4096 for path in labels):
            raise ValueError
        rules = rules_from_json(value.get("field_rules", []))
        for rule in rules:
            _labels({"": rule.label}, anon)
        exclusions = _field_exclusions(value.get("field_person_exclusions"))
        return {**core, "field_labels": labels,
                "field_rules": [{"path": [None if p is EACH else p for p in rule.path],
                                 "label": rule.label, "required": rule.required} for rule in rules],
                "field_person_exclusions": {path: sorted(terms) for path, terms in exclusions.items()}}
    except (TypeError, ValueError):
        raise ValueError("invalid structured core policy; use bounded field settings without external state") from None


@dataclass(frozen=True, init=False)
class PolicyProfile:
    """An immutable snapshot of validated settings; each process uses a new Vault.

    Settings may contain sensitive exclusion terms or field names. The repr
    hides them; exported dictionaries/JSON do not. The fingerprint identifies
    normalized settings, not privacy guarantees, source data or Vault contents.
    """

    _json: str = field(repr=False)
    name: str = field(repr=False)

    def __init__(self, settings: Mapping[str, Any], *, name: str = "") -> None:
        if not isinstance(settings, Mapping) or not settings.keys() <= CORE_OPTIONS | FIELD_OPTIONS:
            raise ValueError("profile requires core/field settings, not executable options")
        normalized = structured_settings(settings) if settings.keys() & FIELD_OPTIONS else core_settings(settings)
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded) > 100_000 or len(encoded.encode("utf-8")) > 400_000:
            raise ValueError("policy profile exceeds size limit")
        object.__setattr__(self, "_json", encoded)
        object.__setattr__(self, "name", _name(name))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PolicyProfile:
        settings = _unwrap(value)
        return cls(settings, name=value.get("name", "") if "schema_version" in value else "")

    @classmethod
    def from_json(cls, text: str) -> PolicyProfile:
        if not isinstance(text, str) or len(text) > 100_000 or len(text.encode("utf-8")) > 400_000:
            raise ValueError("policy profile requires bounded JSON")
        return cls.from_dict(loads_json(text))

    @property
    def settings(self) -> dict[str, Any]:
        return json.loads(self._json)  # type: ignore[no-any-return]

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()

    @property
    def structured(self) -> bool:
        return bool(self.settings.keys() & FIELD_OPTIONS)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "name": self.name, "settings": self.settings}

    def make_anonymizer(self, *, vault: ReversibleVault | None = None, trace_limit: int = 0) -> Anonymizer:
        settings = {k: v for k, v in self.settings.items() if k in CORE_OPTIONS}
        return Anonymizer(**{**settings, "mode": ProcessingMode(settings["mode"])},
                          vault=vault, trace_limit=trace_limit)

    def structured_options(self) -> dict[str, Any]:
        settings = structured_settings(self)
        return {"field_labels": settings["field_labels"],
                "field_rules": rules_from_json(settings["field_rules"]),
                "field_person_exclusions": settings["field_person_exclusions"]}

    def process(self, text: str) -> AnonymizationResult:
        if self.structured:
            raise ValueError("field settings require process_json or process_jsonl")
        return self.make_anonymizer().process(text)

    def process_json(self, data: Any, *, limits: StructuredLimits | None = None) -> StructuredResult:
        return anonymize_json(data, anonymizer=self.make_anonymizer(), limits=limits, **self.structured_options())

    def process_jsonl(self, text: str, *, limits: StructuredLimits | None = None) -> list[StructuredResult]:
        return anonymize_jsonl(text, anonymizer=self.make_anonymizer(), limits=limits, **self.structured_options())
