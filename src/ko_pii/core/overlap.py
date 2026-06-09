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

from typing import Iterable

from ko_pii.core.types import DetectionResult


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
    accepted: list[DetectionResult] = []
    for d in items:
        if any(d.start < a.end and a.start < d.end for a in accepted):
            continue
        accepted.append(d)
    accepted.sort(key=lambda d: (d.start, d.end))
    return accepted
