"""Bounded name-field syntax, shared by candidate selection and scoring."""
from __future__ import annotations

import re

from ko_pii.dictionaries.field_labels import FIELD_LABELS, FIELD_LABELS_NAME


PERSON_NAME_LABELS = frozenset({"성명", "성함"})


def _labels_pattern(labels: frozenset[str]) -> str:
    canonical = {label.replace(" ", "") for label in labels}
    return "|".join(
        r"[ \t]*".join(re.escape(char) for char in label)
        for label in sorted(canonical, key=lambda value: (-len(value), value))
    )


_LABEL_BEFORE = re.compile(
    r"(?<![가-힣A-Za-z0-9_])(?P<label>(?:" + _labels_pattern(FIELD_LABELS_NAME) + r"))"
    r"(?:[ \t]*\((?:한글|국문|실명)\))?"
    r"(?:[ \t]*[:：=][ \t]*(?:\r?\n[ \t]*)?|[ \t]+|[ \t]*\r?\n[ \t]*)[\"']?\Z"
)
_VALUE_END = re.compile(r" *\Z| *(?=[\r\n\t,;|/().\[\]{}\"'])")
_NEXT_FIELD = re.compile(r" +(?:" + _labels_pattern(FIELD_LABELS) + r")[ \t]*[:：=]")
_LABEL_ENDINGS = frozenset(label[-1] for label in FIELD_LABELS_NAME) | {")"}
_ROLE_BEFORE = re.compile(
    r"(?<![가-힣A-Za-z0-9_])(?P<label>(?:"
    + _labels_pattern(FIELD_LABELS_NAME - PERSON_NAME_LABELS - {"이름", "이 름", "참조"})
    + r"))인[ \t]+\Z"
)


def name_field_before(text: str, start: int, window: int = 6) -> str | None:
    begin = max(0, start - max(window + 4, 32))
    head = text[begin:start].rstrip(" \t\r\n:：=\"'")
    if not head or head[-1] not in _LABEL_ENDINGS:
        return None
    match = _LABEL_BEFORE.search(text, begin, start)
    if match is None:
        return None
    return match.group("label").replace(" ", "").replace("\t", "")


def bounded_name_value_end(text: str, end: int) -> bool:
    return bool(_VALUE_END.match(text, end) or _NEXT_FIELD.match(text, end))


def name_role_before(text: str, start: int) -> str | None:
    """Recognize a person role in prose without treating it as a literal field."""
    begin = max(0, start - 32)
    head = text[begin:start].rstrip(" \t")
    if not head.endswith("인"):
        return None
    match = _ROLE_BEFORE.search(text, begin, start)
    if match is None:
        return None
    return match.group("label").replace(" ", "").replace("\t", "")
