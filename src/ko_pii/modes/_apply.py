"""공통 치환 유틸리티 — DetectionResult 리스트로 문자열을 안전하게 치환."""
from __future__ import annotations

from typing import Callable, Iterable

from ko_pii.core.types import DetectionResult


def _dedup_and_sort(
    detections: Iterable[DetectionResult],
) -> list[DetectionResult]:
    """Sort detections by start offset; drop overlaps (later one dropped).

    Stable ordering rule: longer / earlier match wins. This matches the
    semantics of multi-detector pipelines where, e.g., RRN and CORP_REG could
    both claim the same span and we need a single replacement.
    """
    items = sorted(
        detections,
        key=lambda d: (d.start, -(d.end - d.start)),
    )
    out: list[DetectionResult] = []
    last_end = -1
    for d in items:
        if d.start < last_end:
            continue
        out.append(d)
        last_end = d.end
    return out


def apply_substitutions(
    text: str,
    detections: Iterable[DetectionResult],
    replacer: Callable[[DetectionResult], str],
) -> str:
    """Apply ``replacer`` to each (deduped, sorted) detection span in *text*."""
    ordered = _dedup_and_sort(detections)
    if not ordered:
        return text
    pieces: list[str] = []
    cursor = 0
    for d in ordered:
        if d.start > cursor:
            pieces.append(text[cursor:d.start])
        pieces.append(replacer(d))
        cursor = d.end
    pieces.append(text[cursor:])
    return "".join(pieces)
