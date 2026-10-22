"""Small, local-only adapters for trusted application rules, not a sandbox."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace
import math
import re

from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.labels import ALL_LABELS


def _validate_result(result: DetectionResult, text: str) -> DetectionResult:
    if not isinstance(result, DetectionResult):
        raise ValueError("custom detector must return DetectionResult objects")
    if not isinstance(result.label, str) or result.label not in ALL_LABELS:
        raise ValueError("custom detector must use an existing ko-pii label")
    if (type(result.start) is not int or type(result.end) is not int
            or not 0 <= result.start < result.end <= len(text)):
        raise ValueError("custom detector returned an invalid source span")
    if not isinstance(result.text, str) or result.text != text[result.start:result.end]:
        raise ValueError("custom detector text must equal the source slice")
    if not isinstance(result.risk_level, RiskLevel):
        raise ValueError("custom detector risk_level must be RiskLevel")
    if (type(result.confidence) not in (int, float) or not 0 <= result.confidence <= 1
            or not math.isfinite(result.confidence)):
        raise ValueError("custom detector confidence must be finite and between 0 and 1")
    # Copy only the supported decision fields. Free-form metadata is not needed
    # to apply a custom rule and can accidentally carry unrelated source data.
    return DetectionResult(result.label, result.text, result.start, result.end,
                           result.risk_level, float(result.confidence))


class CallableDetector:
    """Wrap a trusted callable; validate the entire bounded output before yielding.

    Limits bound input/result sizes, not execution time. Callbacks and regular
    expressions run in-process and must not come from untrusted users.
    """

    name = "custom-callable"

    def __init__(self, callback: Callable[[str], Iterable[DetectionResult]], *,
                 max_chars: int = 1_000_000, max_matches: int = 10_000) -> None:
        if not callable(callback):
            raise ValueError("custom detector callback must be callable")
        if any(type(n) is not int or n < 1 for n in (max_chars, max_matches)):
            raise ValueError("custom detector limits must be positive integers")
        self._callback = callback
        self.max_chars = max_chars
        self.max_matches = max_matches

    def detect(self, text: str) -> Iterator[DetectionResult]:
        if not isinstance(text, str) or len(text) > self.max_chars:
            raise ValueError("custom detector input must be a bounded string")
        results: list[DetectionResult] = []
        try:
            for result in self._callback(text):
                if len(results) >= self.max_matches:
                    raise ValueError("custom detector exceeded match limit")
                results.append(_validate_result(result, text))
        except Exception:
            # Callback exceptions may contain source text. Do not reflect it.
            raise ValueError("custom detector failed or returned invalid/beyond-limit results") from None
        yield from results


class RegexDetector(CallableDetector):
    """Match an existing label on original text, optionally using a capture group."""

    name = "custom-regex"

    def __init__(self, pattern: str, *, label: str, group: int | str = 0,
                 risk_level: RiskLevel = RiskLevel.HIGH, confidence: float = 1.0,
                 flags: int = 0, max_chars: int = 1_000_000, max_matches: int = 10_000) -> None:
        if not isinstance(pattern, str) or not pattern or len(pattern) > 4096:
            raise ValueError("custom regex must be a nonempty pattern of at most 4096 characters")
        try:
            compiled = re.compile(pattern, flags)
        except (ValueError, TypeError, re.error):
            raise ValueError("invalid custom regex") from None
        if not (type(group) is int and 0 <= group <= compiled.groups
                or type(group) is str and group in compiled.groupindex):
            raise ValueError("custom regex capture group does not exist")
        template = _validate_result(DetectionResult(label, "x", 0, 1, risk_level, confidence), "x")

        def matches(text: str) -> Iterator[DetectionResult]:
            for match in compiled.finditer(text):
                start, end = match.span(group)
                if start == -1:  # An optional group did not participate.
                    continue
                yield replace(template, start=start, end=end, text=text[start:end])

        super().__init__(matches, max_chars=max_chars, max_matches=max_matches)
