"""공통 치환 유틸리티 — DetectionResult 리스트로 문자열을 안전하게 치환."""
from __future__ import annotations

from typing import Callable, Iterable

from ko_pii.core.types import DetectionResult
# 겹침 해소는 core.overlap 단일 구현 사용 (detect_all 과 동일 우선순위).
from ko_pii.core.overlap import resolve_overlaps as _dedup_and_sort


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
