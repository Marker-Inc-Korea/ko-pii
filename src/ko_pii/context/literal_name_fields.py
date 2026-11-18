"""Name-shaped values in person-specific fields, not a general multilingual NER."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from ko_pii.context.name_fields import next_field_after_name, strong_name_field_starts
from ko_pii.context.particles import PARTICLES, strip_trailing_particle
from ko_pii.dictionaries.surnames import is_surname


MAX_NAME_CHARS = 128
COPULA_ENDINGS = ("이라고", "이라는", "입니다", "이며", "이고", "이라")
_ENDING = re.compile("|".join(re.escape(value) for value in
                            sorted(set(PARTICLES) | set(COPULA_ENDINGS), key=lambda value: (-len(value), value))))
_EMPTY = re.compile(r"(?:n/a|n\.a\.|na|null|none)", re.IGNORECASE)
_WRAPPERS = {"**": "**", "__": "__", "`": "`", '"': '"', "'": "'",
             "“": "”", "‘": "’", "「": "」", "『": "』"}
_SEPARATORS = frozenset(",/&·-")
_VALUE_END = frozenset("\r\n\v\f\x1c\x1d\x1e\x85\u2028\u2029\t,;|/&·-().[]{}!?“”‘’「」『』\"'")


@dataclass(frozen=True)
class LiteralName:
    name: str
    start: int
    end: int
    label: str
    parenthetical: bool = False
    ending: str | None = None
    legacy: bool = False


def _letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _name_char(char: str) -> bool:
    return unicodedata.category(char)[0] in {"L", "M"}


def _word_char(char: str) -> bool:
    return char == "_" or char.isalnum() or _name_char(char)


def _hangul(value: str) -> bool:
    return bool(value) and all("가" <= char <= "힣" for char in unicodedata.normalize("NFC", value))


def _east_asian(char: str) -> bool:
    return unicodedata.name(char, "").startswith(("HANGUL", "CJK "))


def _horizontal(text: str, position: int) -> int:
    while position < len(text) and text[position] == " ":
        position += 1
    return position


def _at_end(text: str, position: int, close: str | None) -> bool:
    tail = _horizontal(text, position)
    return (tail == len(text) or (close is not None and text.startswith(close, tail))
            or (tail < len(text) and text[tail] in _VALUE_END)
            or next_field_after_name(text, position))


def _word_end(text: str, start: int, limit: int) -> int:
    if start >= len(text) or not _letter(text[start]):
        return start
    position = start
    piece_start = start
    while position < min(len(text), limit):
        char = text[position]
        if _name_char(char):
            position += 1
        elif char in "-'’·" and position + 1 < len(text) and _letter(text[position + 1]):
            if _east_asian(text[position - 1]) or _east_asian(text[position + 1]):
                break
            piece_start = position + 1
            position += 1
        elif char == "." and (position - piece_start == 1 or text[piece_start:position].lower() in {"jr", "sr"}):
            position += 1
            piece_start = position
        else:
            break
    return position


def _component(text: str, position: int, label: str, *, parenthetical: bool = False) -> tuple[LiteralName | None, int] | None:
    wrapper = next((value for value in _WRAPPERS if text.startswith(value, position)), None)
    close = _WRAPPERS[wrapper] if wrapper else None
    start = position + len(wrapper or "")
    if wrapper:
        start = _horizontal(text, start)
    limit = start + MAX_NAME_CHARS
    empty = _EMPTY.match(text, start)
    if empty is not None and _at_end(text, empty.end(), close):
        end = empty.end()
        if close:
            closing = _horizontal(text, end)
            if not text.startswith(close, closing):
                return None
            end = closing + len(close)
        return None, end
    words: list[str] = []
    cursor = start
    while True:
        end = _word_end(text, cursor, limit)
        if end == cursor:
            return None
        words.append(text[cursor:end])
        if (end == limit and end < len(text) and not _at_end(text, end, close)
                and (_name_char(text[end]) or text[end] in " -'’·")):
            return None
        if _at_end(text, end, close):
            break
        following = _horizontal(text, end)
        if following == end or following >= limit:
            return None
        cursor = following
    consumed = end
    closing = _horizontal(text, end)
    quoted = close is not None and text.startswith(close, closing)
    if close is not None:
        if not quoted:
            return None
        consumed = closing + len(close)
    if all(_hangul(word) for word in words) and len(words) > 1 and not quoted:
        if len(words) != 2 or not is_surname(unicodedata.normalize("NFC", words[0])):
            return None
    value = text[start:end]
    ending = None
    if _hangul(value) and len(value) > 4:
        ending = next((suffix for suffix in COPULA_ENDINGS
                       if value.endswith(suffix) and len(value) - len(suffix) >= 2), None)
        if ending:
            end -= len(ending)
            value = text[start:end]
        else:
            stem, particle = strip_trailing_particle(value)
            if particle and len(particle) > 1 and 2 <= len(stem) <= 4:
                return LiteralName(stem, start, start + len(stem), label, parenthetical, particle, True), consumed
    legacy = _hangul(value) and 2 <= len(value) <= 4 and not parenthetical
    return LiteralName(value, start, end, label, parenthetical, ending, legacy), consumed


def literal_name_fields(text: str) -> Iterator[LiteralName]:
    for position, label in strong_name_field_starts(text):
        field_values: list[LiteralName] = []
        while position < len(text):
            parsed = _component(text, position, label)
            if parsed is None:
                break
            candidate, position = parsed
            if candidate is not None:
                field_values.append(candidate)
            after = _horizontal(text, position)
            if after < len(text) and text[after] == "(":
                child = _component(text, after + 1, label, parenthetical=True)
                if child is not None:
                    alternative, end = child
                    end = _horizontal(text, end)
                    if end < len(text) and text[end] == ")":
                        if alternative is not None:
                            field_values.append(alternative)
                        after = _horizontal(text, end + 1)
            if after >= len(text) or text[after] not in _SEPARATORS:
                break
            position = _horizontal(text, after + 1)
        if any(not candidate.legacy for candidate in field_values):
            yield from field_values


class _Node:
    def __init__(self) -> None:
        self.children: dict[str, _Node] = {}
        self.terminal = False


def literal_name_mentions(text: str, names: Iterable[str]) -> Iterator[tuple[int, int, str | None]]:
    values = set(names)
    if not values:
        return
    root = _Node()
    for name in values:
        if not name or len(name) > MAX_NAME_CHARS:
            raise ValueError("literal name is outside the supported field bound")
        node = root
        for char in name:
            child = node.children.get(char)
            if child is None:
                child = _Node()
                node.children[char] = child
            node = child
        node.terminal = True
    for start, char in enumerate(text):
        if char not in root.children or (start > 0 and _word_char(text[start - 1])):
            continue
        node = root
        best: tuple[int, int, str | None] | None = None
        for position in range(start, min(len(text), start + MAX_NAME_CHARS)):
            child = node.children.get(text[position])
            if child is None:
                break
            node = child
            end = position + 1
            if not node.terminal:
                continue
            if end == len(text) or not _word_char(text[end]):
                best = start, end, None
            else:
                ending = _ENDING.match(text, end)
                if ending is not None and (ending.end() == len(text) or not _word_char(text[ending.end()])):
                    best = start, end, ending.group(0)
        if best is not None:
            yield best
