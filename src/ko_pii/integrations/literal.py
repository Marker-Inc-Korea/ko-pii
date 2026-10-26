"""Bounded exact-value matching on original text, with opt-in Korean particles."""
from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
import re

from ko_pii.context.particles import PARTICLES
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.integrations.custom import CallableDetector
from ko_pii.labels import ALL_LABELS


class LiteralDetector(CallableDetector):
    """Detect supplied values, not unknown entities or fuzzy spelling variants.

    ``word`` requires Unicode word boundaries; ``substring`` does not.
    ``korean`` additionally permits known particles after all-Hangul PERSON
    values. Matching is case-sensitive, without normalization. Limits fail
    rather than silently truncating the configured dictionary or results.
    """

    name = "custom-literal"

    def __init__(self, values: Mapping[str, Iterable[str]], *, boundary: str = "word",
                 max_chars: int = 1_000_000, max_matches: int = 10_000) -> None:
        if not isinstance(boundary, str) or boundary not in {"word", "substring", "korean"}:
            raise ValueError("literal boundary must be word, substring or korean")
        if not isinstance(values, Mapping) or not values or len(values) > len(ALL_LABELS):
            raise ValueError("literal values require a nonempty label mapping")
        grouped: dict[tuple[str, bool], set[str]] = {}
        owners: dict[str, str] = {}
        count = chars = 0
        try:
            for label, terms in values.items():
                if label not in ALL_LABELS or isinstance(terms, (str, bytes)):
                    raise ValueError
                present = False
                for term in terms:
                    count += 1
                    if not isinstance(term, str) or not term.strip() or len(term) > 256:
                        raise ValueError
                    chars += len(term)
                    if count > 1024 or chars > 65536 or (term in owners and owners[term] != label):
                        raise ValueError
                    owners[term] = label
                    korean = boundary == "korean" and label == "PERSON" and bool(re.fullmatch("[가-힣]+", term))
                    grouped.setdefault((label, korean), set()).add(term)
                    present = True
                if not present:
                    raise ValueError
        except Exception:
            raise ValueError("invalid or beyond-limit literal values; use existing labels and bounded strings") from None
        patterns: list[tuple[str, re.Pattern[str]]] = []
        particles = "|".join(re.escape(p) for p in sorted(PARTICLES, key=lambda p: (-len(p), p)))
        for (label, korean), terms in sorted(grouped.items()):
            alternatives = "|".join(re.escape(t) for t in sorted(terms, key=lambda t: (-len(t), t)))
            left = "" if boundary == "substring" else r"(?<!\w)"
            right = "" if boundary == "substring" else (
                rf"(?=(?:{particles})?(?!\w))" if korean else r"(?!\w)"
            )
            # Lookahead preserves overlapping starts and source offsets. The
            # boundary is inside it so a longer invalid alternative can backtrack.
            patterns.append((label, re.compile(left + "(?=(" + alternatives + ")" + right + ")")))

        def matches(text: str) -> Iterator[DetectionResult]:
            for label, pattern in patterns:
                for match in pattern.finditer(text):
                    start, end = match.span(1)
                    yield DetectionResult(label, text[start:end], start, end, RiskLevel.HIGH, 1.0)

        super().__init__(matches, max_chars=max_chars, max_matches=max_matches)
