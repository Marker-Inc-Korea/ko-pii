"""공통 치환 유틸리티 — DetectionResult 리스트로 문자열을 안전하게 치환."""
from __future__ import annotations

from typing import Callable, Iterable
from dataclasses import dataclass

from ko_pii.core.types import DetectionResult
# 겹침 해소는 core.overlap 단일 구현 사용 (detect_all 과 동일 우선순위).
from ko_pii.core.overlap import resolve_overlaps as _dedup_and_sort


@dataclass(frozen=True)
class AppliedSpan:
    """Source/output coordinates of a substitution actually emitted."""
    start: int
    end: int
    output_start: int
    output_end: int


def apply_substitutions(
    text: str,
    detections: Iterable[DetectionResult],
    replacer: Callable[[DetectionResult], str],
    *,
    trace: list[AppliedSpan] | None = None,
) -> str:
    """Apply ``replacer`` to each (deduped, sorted) detection span in *text*."""
    ordered = _dedup_and_sort(detections)
    if not ordered:
        return text
    pieces: list[str] = []
    cursor = 0
    output_cursor = 0
    for d in ordered:
        if d.start > cursor:
            pieces.append(text[cursor:d.start])
            output_cursor += d.start - cursor
        replacement = replacer(d)
        pieces.append(replacement)
        if trace is not None:
            trace.append(AppliedSpan(d.start, d.end, output_cursor, output_cursor + len(replacement)))
        output_cursor += len(replacement)
        cursor = d.end
    pieces.append(text[cursor:])
    return "".join(pieces)
