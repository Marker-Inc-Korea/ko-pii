"""겹침 해소 — 단일 정본 구현.

detect_all / merge_detections / 치환(apply_substitutions) 경로가 **모두 같은 우선순위**로
겹침을 해소하도록 한 곳에 둔다. 과거 각 경로가 별도 구현을 갖고 우선순위가 달라
(특히 integrations/hybrid 의 start-우선 정렬) **늦게 시작하는 고위험 PII(주민·전화)가
먼저 시작한 저위험 span(과매칭 주소·URL)에 가려 평문 누출**되는 회귀가 가능했다.

정책: 위험도 → 확신도 → 길이 순으로 채택(높을수록 먼저), 이미 채택된 span 과 겹치면 드롭.
*시작 위치*가 아니라 *우선순위*로 정렬하는 것이 핵심 — 늦게 시작하는 고위험 PII 도 살아남는다.
반환은 문서 순서(start, end).
"""
from __future__ import annotations

from bisect import bisect_left
from typing import Iterable

from ko_pii.core.types import DetectionResult


def _select_non_overlapping(items: list[DetectionResult]) -> list[DetectionResult]:
    """Keep the first eligible spans in input order in O(n log n) time.

    An accepted interval overlaps a candidate iff its start is below the
    candidate's end and its end is above the candidate's start. A Fenwick tree
    stores prefix maxima of ends, indexed by compressed start coordinates.
    This preserves the original strict inequalities, including empty spans.
    """
    starts = sorted({d.start for d in items})
    positions = {start: i + 1 for i, start in enumerate(starts)}
    ends: list[int | None] = [None] * (len(starts) + 1)
    accepted: list[DetectionResult] = []
    for d in items:
        i = bisect_left(starts, d.end)
        overlaps = False
        while i:
            end = ends[i]
            if end is not None and end > d.start:
                overlaps = True
                break
            i -= i & -i
        if overlaps:
            continue
        accepted.append(d)
        i = positions[d.start]
        while i < len(ends):
            end = ends[i]
            if end is None or d.end > end:
                ends[i] = d.end
            i += i & -i
    return accepted


def resolve_overlaps(detections: Iterable[DetectionResult]) -> list[DetectionResult]:
    items = sorted(
        detections,
        key=lambda d: (
            -int(d.risk_level),
            -d.confidence,
            -(d.end - d.start),
            d.start,
        ),
    )
    accepted = _select_non_overlapping(items)
    accepted.sort(key=lambda d: (d.start, d.end))
    return accepted
