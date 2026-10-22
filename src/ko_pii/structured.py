"""Bounded JSON transformations. Keys are preserved, never implicitly screened."""
from __future__ import annotations

from collections.abc import Mapping, Iterable
from dataclasses import dataclass, field
import json
import math
import re
from typing import Any

from ko_pii.anonymizer import Anonymizer, AnonymizationResult
from ko_pii.core.modes import ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.labels import validate_label_filter
from ko_pii.reporting.explanation import explain
from ko_pii.field_rules import FieldRule, bounded_rules, resolve_rules


@dataclass(frozen=True)
class StructuredLimits:
    max_depth: int = 64
    max_nodes: int = 100_000
    max_chars: int = 10_000_000
    max_string_chars: int = 1_000_000
    max_documents: int = 10_000

    def __post_init__(self) -> None:
        for value in (self.max_depth, self.max_nodes, self.max_chars,
                      self.max_string_chars, self.max_documents):
            if type(value) is not int or value < 1:
                raise ValueError("structured limits must be positive integers")
        if self.max_depth > 128:
            raise ValueError("max_depth must not exceed 128")


@dataclass
class StructuredField:
    path: str
    result: AnonymizationResult


@dataclass
class StructuredResult:
    data: Any
    fields: list[StructuredField] = field(default_factory=list)
    source_line: int | None = None
    field_rule_summary: list[dict[str, Any]] = field(default_factory=list)

    def report(self, *, include_paths: bool = False) -> dict[str, Any]:
        """Paths are opt-in because object keys can themselves contain PII."""
        rows = []
        for index, item in enumerate(self.fields):
            row = {"field_index": index, **explain(item.result)}
            if include_paths:
                row["path"] = item.path
            rows.append(row)
        return {"schema_version": 1, "contract": "ko-pii-structured-explanation-v1",
                "scope": "string_values_and_asserted_integer_fields", "keys_screened": False,
                "source_line": self.source_line, "field_rules": self.field_rule_summary, "fields": rows}


def _pointer(parent: str, key: str) -> str:
    return parent + "/" + key.replace("~", "~0").replace("/", "~1")


def _labels(field_labels: Mapping[str, str] | None, anon: Anonymizer) -> dict[str, str]:
    if field_labels is not None and not isinstance(field_labels, Mapping):
        raise ValueError("field_labels must be a mapping of exact JSON Pointers")
    labels = dict(field_labels or {})
    for path, label in labels.items():
        if not isinstance(path, str) or (path and not path.startswith("/")) or re.search(r"~(?![01])", path):
            raise ValueError("field_labels contains an invalid JSON Pointer")
        validate_label_filter([label], name="field_labels")
        if (anon.include is not None and label not in anon.include) or (anon.exclude and label in anon.exclude):
            raise ValueError("field_labels conflicts with include/exclude filters")
    return labels


def _validate(data: Any, labels: dict[str, str], limits: StructuredLimits) -> None:
    nodes = 0
    characters = 0
    ancestors: set[int] = set()
    seen: set[str] = set()

    def count_text(text: str) -> None:
        nonlocal characters
        characters += len(text)
        if len(text) > limits.max_string_chars or characters > limits.max_chars:
            raise ValueError("structured input exceeds character limits")
        if any(0xD800 <= ord(c) <= 0xDFFF for c in text):
            raise ValueError("structured input contains an invalid Unicode surrogate")

    def visit(value: Any, path: str, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes or depth > limits.max_depth:
            raise ValueError("structured input exceeds node or depth limits")
        if path in labels:
            seen.add(path)
            if value is not None and type(value) not in (str, int):
                raise ValueError("asserted fields must be strings, integers or null; floats are unsafe identifiers")
        if type(value) is str:
            count_text(value)
        elif value is None or type(value) is bool:
            return
        elif type(value) is int:
            try:
                count_text(str(value))
            except ValueError:
                raise ValueError("structured integer exceeds conversion limits") from None
        elif type(value) is float:
            if not math.isfinite(value):
                raise ValueError("structured input must contain finite JSON numbers")
        elif type(value) in (dict, list):
            if id(value) in ancestors:
                raise ValueError("structured input contains a cycle")
            ancestors.add(id(value))
            if isinstance(value, dict):
                for key, child in value.items():
                    if type(key) is not str:
                        raise ValueError("JSON object keys must be strings")
                    count_text(key)
                    visit(child, _pointer(path, key), depth + 1)
            else:
                for index, child in enumerate(value):
                    visit(child, _pointer(path, str(index)), depth + 1)
            ancestors.remove(id(value))
        else:
            raise ValueError("structured input contains a non-JSON value")

    visit(data, "", 0)
    if set(labels) != seen:
        raise ValueError("field_labels contains a path absent from the document")


def anonymize_json(
    data: Any, *, anonymizer: Anonymizer | None = None,
    field_labels: Mapping[str, str] | None = None,
    limits: StructuredLimits | None = None,
    field_rules: Iterable[FieldRule] | None = None,
) -> StructuredResult:
    """Copy and process JSON values with one shared Anonymizer/Vault.

    Explicit fields are label assertions, not guesses: their whole string/int
    is transformed regardless of detection thresholds (except in AUDIT mode).
    Integers become strings only when transformed. Keys are preserved. No claim
    is made about PII in keys, ordinary numbers, or undetected string values.
    """
    anon = anonymizer if anonymizer is not None else Anonymizer()
    policy = limits or StructuredLimits()
    labels = _labels(field_labels, anon)
    _validate(data, labels, policy)
    rules = bounded_rules(field_rules)
    for rule in rules:
        _labels({"": rule.label}, anon)
    labels, rule_summary = resolve_rules(data, labels, rules)
    _validate(data, labels, policy)
    fields: list[StructuredField] = []

    def transform(value: Any, path: str) -> Any:
        label = labels.get(path)
        if label is not None and value is not None:
            text = str(value)
            detections = [DetectionResult(
                label, text, 0, len(text), RiskLevel.HIGH,
                evidence=["field:asserted"], rule_id="field.asserted.v1",
            )] if text else []
            result = anon._process_detections(text, detections, asserted=True)
            fields.append(StructuredField(path, result))
            return value if anon.mode == ProcessingMode.AUDIT else result.text
        if type(value) is str:
            result = anon.process(value)
            fields.append(StructuredField(path, result))
            return result.text
        if type(value) is dict:
            return {key: transform(child, _pointer(path, key)) for key, child in value.items()}
        if type(value) is list:
            return [transform(child, _pointer(path, str(index))) for index, child in enumerate(value)]
        return value

    return StructuredResult(transform(data, ""), fields, field_rule_summary=rule_summary)


def loads_json(text: str, *, limits: StructuredLimits | None = None) -> Any:
    """Strict bounded JSON parsing, without reflecting invalid source in errors."""
    policy = limits or StructuredLimits()
    if not isinstance(text, str) or len(text) > policy.max_chars:
        raise ValueError("JSON input exceeds character limits")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> Any:
        raise ValueError("non-finite JSON number")

    try:
        data = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError):
        raise ValueError("invalid JSON, duplicate key, non-finite number or excessive nesting") from None
    _validate(data, {}, policy)
    return data


def anonymize_jsonl(
    text: str, *, anonymizer: Anonymizer | None = None,
    field_labels: Mapping[str, str] | None = None,
    limits: StructuredLimits | None = None,
    field_rules: Iterable[FieldRule] | None = None,
) -> list[StructuredResult]:
    """Validate the entire bounded input before processing; no partial return.

    Shared Vault state can still change if a detector fails during processing.
    This function is not a transaction across an external Vault/audit service.
    """
    policy = limits or StructuredLimits()
    if not isinstance(text, str) or len(text) > policy.max_chars:
        raise ValueError("JSONL input exceeds character limits")
    anon = anonymizer if anonymizer is not None else Anonymizer()
    labels = _labels(field_labels, anon)
    rules = bounded_rules(field_rules)
    for rule in rules:
        _labels({"": rule.label}, anon)
    documents: list[tuple[int, Any]] = []
    for number, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        if len(documents) >= policy.max_documents:
            raise ValueError("JSONL input exceeds document limits")
        try:
            data = loads_json(line, limits=policy)
            _validate(data, labels, policy)
            resolved, _ = resolve_rules(data, labels, rules)
            _validate(data, resolved, policy)
        except ValueError:
            raise ValueError(f"invalid JSONL document at line {number}") from None
        documents.append((number, data))
    if not documents:
        raise ValueError("JSONL input must contain at least one document")
    results = []
    for number, data in documents:
        result = anonymize_json(data, anonymizer=anon, field_labels=labels, limits=policy, field_rules=rules)
        result.source_line = number
        results.append(result)
    return results
