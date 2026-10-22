"""Explicit typed selectors; literal '*' keys are not array wildcards."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ko_pii.labels import ALL_LABELS


class ArrayItems(Enum):
    EACH = "each_array_item"


EACH = ArrayItems.EACH


@dataclass(frozen=True)
class FieldRule:
    path: tuple[str | int | ArrayItems, ...]
    label: str
    required: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.path, tuple) or len(self.path) > 128:
            raise ValueError("field rule path must be a tuple of at most 128 segments")
        for segment in self.path:
            if not (type(segment) is str or type(segment) is int and segment >= 0 or segment is EACH):
                raise ValueError("field rule segments must be keys, nonnegative indices or EACH")
        if not isinstance(self.label, str) or self.label not in ALL_LABELS or type(self.required) is not bool:
            raise ValueError("invalid field rule label or required flag")


def bounded_rules(rules: Iterable[FieldRule] | None) -> tuple[FieldRule, ...]:
    result: list[FieldRule] = []
    for rule in rules if rules is not None else ():
        if not isinstance(rule, FieldRule) or len(result) >= 128:
            raise ValueError("field rules must contain at most 128 FieldRule objects")
        result.append(rule)
    return tuple(result)


def rules_from_json(data: Any) -> tuple[FieldRule, ...]:
    """In JSON configuration only, a null path segment denotes EACH."""
    if not isinstance(data, list) or len(data) > 128:
        raise ValueError("field rules configuration must be a bounded list")
    rules = []
    for row in data:
        if (not isinstance(row, dict) or not {"path", "label"} <= row.keys()
                or not row.keys() <= {"path", "label", "required"} or not isinstance(row["path"], list)):
            raise ValueError("invalid field rules configuration")
        rules.append(FieldRule(tuple(EACH if p is None else p for p in row["path"]),
                               row["label"], row.get("required", True)))
    return bounded_rules(rules)


def resolve_rules(
    data: Any, labels: dict[str, str], rules: tuple[FieldRule, ...],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Resolve only after the JSON tree has passed size/cycle validation."""
    resolved = dict(labels)
    reports = []
    for index, rule in enumerate(rules):
        stats = {"matched": 0, "missing": 0, "empty_arrays": 0, "null_fields": 0}

        def visit(value: Any, depth: int, pointer: str) -> None:
            if depth == len(rule.path):
                if pointer in resolved and resolved[pointer] != rule.label:
                    raise ValueError(f"conflicting field labels at rule {index}")
                resolved[pointer] = rule.label
                stats["matched"] += 1
                stats["null_fields"] += int(value is None)
                return
            segment = rule.path[depth]
            if segment is EACH:
                if not isinstance(value, list):
                    raise ValueError(f"field rule {index} expected an array")
                stats["empty_arrays"] += int(not value)
                for position, child in enumerate(value):
                    visit(child, depth + 1, f"{pointer}/{position}")
                return
            if type(segment) is str and isinstance(value, dict):
                exists = segment in value
            elif type(segment) is int and isinstance(value, list):
                exists = segment < len(value)
            else:
                raise ValueError(f"field rule {index} encountered an incompatible container")
            if not exists:
                stats["missing"] += 1
                if rule.required:
                    raise ValueError(f"required field missing at rule {index}")
                return
            key = str(segment).replace("~", "~0").replace("/", "~1")
            visit(value[segment], depth + 1, pointer + "/" + key)

        visit(data, 0, "")
        reports.append({"rule_index": index, "label": rule.label, "required": rule.required, **stats})
    return resolved, reports
