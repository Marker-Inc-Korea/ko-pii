"""Bounded name-field syntax, shared by candidate selection and scoring."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

from ko_pii.dictionaries.field_labels import FIELD_BOUNDARY_LABELS, FIELD_LABELS_NAME
from ko_pii.dictionaries.table_headers import ENGLISH_SUBJECTS, KOREAN_SUBJECTS


PERSON_NAME_LABELS = frozenset({"성명", "성함"})
_LINE_BREAK_CHARS = "\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029"
_GAP = "[" + re.escape(" \t" + _LINE_BREAK_CHARS) + "]"
_OPENING_QUOTES = "\"'\u201c\u2018\u300c\u300e"
_CLOSING_QUOTES = "\"'\u201d\u2019\u300d\u300f"


def _labels_pattern(labels: frozenset[str]) -> str:
    canonical = {label.replace(" ", "") for label in labels}
    return "|".join(
        r"[ \t]*".join(re.escape(char) for char in label)
        for label in sorted(canonical, key=lambda value: (-len(value), value))
    )


def _label_prefix(labels: frozenset[str]) -> str:
    return (
        r"(?<!\w)"
        r"(?:(?P<square>\[)|(?P<corner>【)|(?P<bold>\*\*)|(?P<strong>__)|(?P<code>`))?"
        r"(?P<label>(?:" + _labels_pattern(labels) + r"))"
        r"(?:[ \t]*\((?:한글|국문|실명|영문|영어|한자)\))?"
        r"(?(square)\])(?(corner)】)(?(bold)\*\*)(?(strong)__)(?(code)`)"
        r"(?:[ \t]*[:：=|]" + _GAP + r"*|" + _GAP + r"+)"
    )


_LABEL_BEFORE = re.compile(_label_prefix(FIELD_LABELS_NAME)
                          + r"(?:\*\*|__|`|[" + re.escape(_OPENING_QUOTES) + r"])?\Z")
_STRONG_FIELD = re.compile(_label_prefix(PERSON_NAME_LABELS))
_VALUE_END = re.compile(r" *\Z| *(?=[" + re.escape(_LINE_BREAK_CHARS + "\t,;|/&().[]{}-·*_`" + _CLOSING_QUOTES) + r"])")
_ANNOTATION = r" *\([^" + re.escape("()\t" + _LINE_BREAK_CHARS) + r"]{0,32}\)"
_SUBJECT = (r"(?:(?:" + "|".join(map(re.escape, KOREAN_SUBJECTS)) + r")[ _-]*"
            r"|(?:" + "|".join(map(re.escape, ENGLISH_SUBJECTS)) + r")[ _-]+)")
_NEXT_FIELD = re.compile(
    r" +(?P<next_subject>" + _SUBJECT + r")?"
    r"(?:(?P<next_square>\[)|(?P<next_corner>【)|(?P<next_bold>\*\*)|(?P<next_strong>__)|(?P<next_code>`))?"
    r"(?(next_subject)|(?:" + _SUBJECT + r")?)"
    r"(?:" + _labels_pattern(FIELD_BOUNDARY_LABELS) + r")"
    r"(?P<next_annotation>" + _ANNOTATION + r")?"
    r"(?(next_square)\])(?(next_corner)】)(?(next_bold)\*\*)(?(next_strong)__)(?(next_code)`)"
    r"(?(next_annotation)|(?:" + _ANNOTATION + r")?)"
    r"[ \t]*[:：=]", re.IGNORECASE,
)
_LABEL_ENDINGS = frozenset(label[-1] for label in FIELD_LABELS_NAME) | {")", "]", "】", "*", "_", "`"}
_LIST_SEPARATOR = re.compile(
    r"[ \t]*(?:(?:\*\*|__|`|[" + re.escape(_CLOSING_QUOTES) + r"])[ \t]*)?"
    r"[,/&·-][ \t]*(?:(?:\*\*|__|`|[" + re.escape(_OPENING_QUOTES) + r"])[ \t]*)?\Z"
)
_ROLE_BEFORE = re.compile(
    r"(?<![가-힣A-Za-z0-9_])(?P<label>(?:"
    + _labels_pattern(FIELD_LABELS_NAME - {"참조"})
    + r"))(?:은|는|이|가|인)[ \t]+\Z"
)


def name_field_before(text: str, start: int, window: int = 6) -> str | None:
    begin = max(0, start - max(window + 4, 32))
    head = text[begin:start].rstrip(" \t:：=|*_`" + _OPENING_QUOTES + _LINE_BREAK_CHARS)
    if not head or head[-1] not in _LABEL_ENDINGS:
        return None
    match = _LABEL_BEFORE.search(text, begin, start)
    if match is None or not _label_boundary(text, match.start()):
        return None
    return match.group("label").replace(" ", "").replace("\t", "")


def bounded_name_value_end(text: str, end: int) -> bool:
    return bool(_VALUE_END.match(text, end) or _NEXT_FIELD.match(text, end))


def strong_name_field_starts(text: str) -> Iterator[tuple[int, str]]:
    for match in _STRONG_FIELD.finditer(text):
        if _label_boundary(text, match.start()):
            yield match.end(), match.group("label").replace(" ", "").replace("\t", "")


def _label_boundary(text: str, start: int) -> bool:
    # Python's \w excludes combining marks, which still belong to a preceding word.
    return start == 0 or not unicodedata.category(text[start - 1]).startswith("M")


def next_field_after_name(text: str, end: int) -> bool:
    return _NEXT_FIELD.match(text, end) is not None


def name_list_separator(text: str, start: int, end: int) -> bool:
    """List context stays in one cell/line, never across arbitrary prose."""
    return _LIST_SEPARATOR.fullmatch(text, start, end) is not None


def name_role_before(text: str, start: int) -> str | None:
    """Recognize a person role in prose without treating it as a literal field."""
    begin = max(0, start - 32)
    head = text[begin:start].rstrip(" \t")
    if not head.endswith(("은", "는", "이", "가", "인")):
        return None
    match = _ROLE_BEFORE.search(text, begin, start)
    if match is None:
        return None
    return match.group("label").replace(" ", "").replace("\t", "")
