"""겹침 해소 — 단일 정본 구현.

detect_all / merge_detections / 치환(apply_substitutions)의 겹침 선택 구현을 한 곳에 둔다.
Anonymizer 병합은 현재 정책의 BLOCK 후보를 우선하고 나머지 순서는 공유한다.
과거 각 경로가 별도 구현을 갖고 우선순위가 달라
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
from ko_pii.core.trace import OverlapTrace
from ko_pii.core.modes import Action, ModePolicy


def _select_non_overlapping(
    items: list[DetectionResult], *, trace: OverlapTrace | None = None, stage: str = "primary",
    policy: ModePolicy | None = None,
) -> list[DetectionResult]:
    """Keep the first eligible spans in input order in O(n log n) time.

    An accepted interval overlaps a candidate iff its start is below the
    candidate's end and its end is above the candidate's start. A Fenwick tree
    stores prefix maxima of ends, indexed by compressed start coordinates.
    This preserves the original strict inequalities, including empty spans.
    """
    starts = sorted({d.start for d in items})
    positions = {start: i + 1 for i, start in enumerate(starts)}
    ends: list[DetectionResult | None] = [None] * (len(starts) + 1)
    accepted: list[DetectionResult] = []
    for d in items:
        i = bisect_left(starts, d.end)
        blocker = None
        while i:
            end = ends[i]
            if end is not None and end.end > d.start:
                blocker = end
                break
            i -= i & -i
        if trace is not None:
            trace.record(d, blocker, stage, policy=policy)
        if blocker is not None:
            continue
        accepted.append(d)
        i = positions[d.start]
        while i < len(ends):
            end = ends[i]
            if end is None or d.end > end.end:
                ends[i] = d
            i += i & -i
    return accepted


def resolve_overlaps(
    detections: Iterable[DetectionResult], *, trace: OverlapTrace | None = None, stage: str = "primary",
    policy: ModePolicy | None = None,
) -> list[DetectionResult]:
    # At the transformation boundary, non-blocking guesses must not displace
    # a candidate that the caller's policy would actually mask.
    items = sorted(
        detections,
        key=lambda d: (
            -(policy is not None and policy.decide(d.risk_level, d.confidence) == Action.BLOCK),
            -int(d.risk_level),
            -d.confidence,
            -(d.end - d.start),
            d.start,
        ),
    )
    accepted = _select_non_overlapping(items, trace=trace, stage=stage, policy=policy)
    accepted.sort(key=lambda d: (d.start, d.end))
    return accepted
