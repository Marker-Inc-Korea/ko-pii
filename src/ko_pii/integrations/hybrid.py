"""두 검출기 (primary + secondary) 결과 병합 로직.

병합 모드:
- ``UNION``: 양쪽 검출 결과 *합산* (overlap 해소) — 가장 일반적 (Method A)
- ``INTERSECTION``: 양쪽 모두 찾은 것만 인정 (높은 신뢰도, Method B 일부)
- ``CROSS_VALIDATION``: 일치=BLOCK / 불일치=REVIEW (Method B 완전)
- ``ENRICH_PRIMARY``: primary 우선, secondary 가 *놓친 영역* 만 보강 (Method C)
- ``FALLBACK_SECONDARY``: primary 의 REVIEW 만 secondary 에 위임 (Method D)

Overlap 해소 우선순위 (기본):
1. risk_level 높은 쪽
2. length 긴 쪽
3. primary (ko-pii) 우선 — 한국 공공 도메인 fit + 법적 근거
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult


class MergeMode(str, Enum):
    UNION = "union"
    INTERSECTION = "intersection"
    CROSS_VALIDATION = "cross_validation"
    ENRICH_PRIMARY = "enrich_primary"
    FALLBACK_SECONDARY = "fallback_secondary"


def _spans_overlap(a: DetectionResult, b: DetectionResult) -> bool:
    return a.start < b.end and b.start < a.end


def _same_label(a: DetectionResult, b: DetectionResult) -> bool:
    # ko-pii 의 카테고리 호환 — 동일 라벨이면 일치
    return a.label == b.label


def _prefer(a: DetectionResult, b: DetectionResult) -> DetectionResult:
    """Overlap 해소 — 위험도 > 길이 > confidence > primary 우선."""
    if int(a.risk_level) != int(b.risk_level):
        return a if int(a.risk_level) > int(b.risk_level) else b
    la = a.end - a.start
    lb = b.end - b.start
    if la != lb:
        return a if la > lb else b
    if a.confidence != b.confidence:
        return a if a.confidence > b.confidence else b
    return a  # tie → primary 우선


def _enrich_with_secondary_info(
    primary: DetectionResult, secondary: DetectionResult
) -> DetectionResult:
    """primary 에 secondary 의 신뢰도·증거 추가."""
    new_extra = dict(primary.extra)
    new_extra["secondary_confirmed_by"] = secondary.evidence
    new_extra["secondary_label"] = secondary.label
    new_evidence = list(primary.evidence) + [
        f"corroborated_by:secondary({secondary.label})"
    ]
    return DetectionResult(
        label=primary.label,
        text=primary.text,
        start=primary.start,
        end=primary.end,
        risk_level=primary.risk_level,
        confidence=min(1.0, primary.confidence + 0.05),  # 약간 부스트
        evidence=new_evidence,
        legal_basis=primary.legal_basis,
        extra=new_extra,
    )


def merge_detections(
    primary: Iterable[DetectionResult],
    secondary: Iterable[DetectionResult],
    mode: MergeMode = MergeMode.UNION,
) -> list[DetectionResult]:
    """primary + secondary 검출 결과를 ``mode`` 에 따라 병합.

    Returns
    -------
    list[DetectionResult] — overlap 해소되고 정렬된 결과.
    """
    primary_list = list(primary)
    secondary_list = list(secondary)

    if mode == MergeMode.INTERSECTION:
        # 양쪽 모두 찾은 것만 인정
        out: list[DetectionResult] = []
        for p in primary_list:
            for s in secondary_list:
                if _spans_overlap(p, s) and _same_label(p, s):
                    out.append(_enrich_with_secondary_info(p, s))
                    break
        return _resolve_overlaps(out)

    if mode == MergeMode.ENRICH_PRIMARY:
        # primary 우선, secondary 는 primary 가 *놓친* 영역만 추가
        out = list(primary_list)
        for s in secondary_list:
            overlaps_primary = any(_spans_overlap(s, p) for p in primary_list)
            if not overlaps_primary:
                out.append(s)
            else:
                # primary 가 잡은 같은 spans 에 secondary corroboration 추가
                for i, p in enumerate(out):
                    if _spans_overlap(p, s) and _same_label(p, s):
                        out[i] = _enrich_with_secondary_info(p, s)
                        break
        return _resolve_overlaps(out)

    if mode == MergeMode.CROSS_VALIDATION:
        # 일치 = high confidence / 불일치 = secondary 결과는 REVIEW 카테고리로
        # (이 모드는 정책 결정을 Anonymizer 에서 함 — 여기서는 결과만 합산)
        out = list(primary_list)
        for s in secondary_list:
            corroborated = False
            for i, p in enumerate(out):
                if _spans_overlap(p, s) and _same_label(p, s):
                    out[i] = _enrich_with_secondary_info(p, s)
                    corroborated = True
                    break
            if not corroborated:
                # secondary 단독 검출 — 신뢰도 낮춤 (cross-val 미통과)
                lowered = DetectionResult(
                    label=s.label,
                    text=s.text,
                    start=s.start,
                    end=s.end,
                    risk_level=s.risk_level,
                    confidence=s.confidence * 0.7,  # cross-val 미통과 페널티
                    evidence=list(s.evidence) + ["uncorroborated:primary_missed"],
                    legal_basis=s.legal_basis,
                    extra={**dict(s.extra), "cross_val": "secondary_only"},
                )
                out.append(lowered)
        return _resolve_overlaps(out)

    if mode == MergeMode.FALLBACK_SECONDARY:
        # primary 결과만 반환 — secondary 는 *호출 시점에서* REVIEW 만
        # 다시 평가하도록 사용 (Anonymizer 가 처리)
        return _resolve_overlaps(primary_list)

    # UNION (기본)
    return _resolve_overlaps(primary_list + secondary_list)


def _resolve_overlaps(detections: list[DetectionResult]) -> list[DetectionResult]:
    """Sort + overlap 해소 — 같은 span 에 여러 검출이면 우선순위 따라 단일."""
    items = sorted(
        detections,
        key=lambda d: (
            d.start,
            -int(d.risk_level),
            -(d.end - d.start),
            -d.confidence,
        ),
    )
    out: list[DetectionResult] = []
    occupied_end = -1
    for d in items:
        if d.start < occupied_end:
            continue
        out.append(d)
        occupied_end = max(occupied_end, d.end)
    return out
