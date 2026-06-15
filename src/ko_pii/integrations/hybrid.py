"""두 검출기 (primary + secondary) 결과 병합 로직.

병합 모드:
- ``UNION``: 양쪽 검출 결과 *합산* (overlap 해소) — 가장 일반적 (Method A)
- ``INTERSECTION``: 양쪽 모두 찾은 것만 인정 (높은 신뢰도, Method B 일부)
- ``CROSS_VALIDATION``: 일치=BLOCK / 불일치=REVIEW (Method B 완전)
- ``ENRICH_PRIMARY``: primary 우선, secondary 가 *놓친 영역* 만 보강 (Method C)
- ``FALLBACK_SECONDARY``: primary 의 REVIEW 만 secondary 에 위임 (Method D)
- ``ROLE_SPLIT``: **역할 분담** — 퍼지 카테고리(이름·주소·직책 등)는 secondary(ML)가
  *교체* 담당, 나머지(결정적 ID 등)는 primary(룰)만 담당 (Method E).
  ``docs/HYBRID_NER.md`` 의 하이브리드 구성(외부 검증 F1 0.97)이 이 모드 —
  union 은 양쪽 FP 가 합산돼 항상 role_split 이하임이 실측됨.

Overlap 해소: ``core.overlap.resolve_overlaps`` 단일 구현 사용
(위험도 → 확신도 → 길이 순, ``detect_all`` 과 동일 — 늦게 시작하는 고위험 PII 누출 차단).
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
# 겹침 해소는 core.overlap 단일 구현 사용 — detect_all 과 동일 우선순위로 통일해
# 병합 경로에서 늦게 시작하는 고위험 PII(주민·전화)가 누출되던 회귀를 차단.
from ko_pii.core.overlap import resolve_overlaps as _resolve_overlaps


class MergeMode(str, Enum):
    UNION = "union"
    INTERSECTION = "intersection"
    CROSS_VALIDATION = "cross_validation"
    ENRICH_PRIMARY = "enrich_primary"
    FALLBACK_SECONDARY = "fallback_secondary"
    ROLE_SPLIT = "role_split"


#: ROLE_SPLIT 기본 위임 라벨 — secondary(ML)가 교체 담당하는 퍼지 카테고리.
#: 룰이 체크섬·패턴으로 강한 결정적 ID(RRN/CARD/PHONE/EMAIL 등)는 primary 유지.
#: (HYBRID_NER.md 의 하이브리드 정의와 동일한 10종.)
DEFAULT_ROLE_SPLIT_LABELS: frozenset[str] = frozenset({
    "PERSON", "ADDRESS", "POSITION", "EDUCATION", "MAJOR",
    "NATIONALITY", "AGE", "DT_BIRTH", "HEIGHT", "WEIGHT",
})


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
    role_split_labels: Optional[Iterable[str]] = None,
) -> list[DetectionResult]:
    """primary + secondary 검출 결과를 ``mode`` 에 따라 병합.

    Parameters
    ----------
    role_split_labels :
        ``ROLE_SPLIT`` 모드에서 secondary 가 담당할 라벨 집합.
        미지정 시 :data:`DEFAULT_ROLE_SPLIT_LABELS` (퍼지 10종).

    Returns
    -------
    list[DetectionResult] — overlap 해소되고 정렬된 결과.
    """
    primary_list = list(primary)
    secondary_list = list(secondary)

    if mode == MergeMode.ROLE_SPLIT:
        # 역할 분담 — 위임 라벨은 secondary 로 *교체*(primary 의 해당 라벨 폐기),
        # 나머지 라벨은 primary 만. 합산(union)이 아니라 교체라는 점이 핵심:
        # 약한 쪽의 FP 가 강한 쪽의 검출을 오염시키지 않는다.
        delegated = (frozenset(role_split_labels) if role_split_labels is not None
                     else DEFAULT_ROLE_SPLIT_LABELS)
        out: list[DetectionResult] = [
            p for p in primary_list if p.label not in delegated
        ]
        out += [s for s in secondary_list if s.label in delegated]
        return _resolve_overlaps(out)

    if mode == MergeMode.INTERSECTION:
        # 양쪽 모두 찾은 것만 인정
        out = []
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


# _resolve_overlaps 는 상단 import 의 core.overlap.resolve_overlaps (정본).
# (이전엔 여기서 start-우선 단일커서로 따로 구현돼, 늦게 시작하는 고위험 PII 가
#  먼저 시작한 저위험 span 에 가려 평문 누출되는 회귀가 있었음 — 정본으로 통일해 해결.)
