"""All-detector entry point — 모든 카테고리 검출기를 한 번에 실행."""
from __future__ import annotations

from typing import Iterable, Iterator, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.core.unicode_norm import normalize_unicode, remap_to_source
from ko_pii.domain import civil_petition as _dom_petition
from ko_pii.domain import government as _dom_gov
from ko_pii.domain import hr as _dom_hr
from ko_pii.patterns import (
    account,
    address,
    birth,
    business_reg,
    card,
    corp_reg,
    court_case,
    driver_license,
    edi_drug,
    email,
    fax,
    frn,
    ip,
    medical_insurance,
    nationality,
    passport,
    person,
    personal_attr,
    phone,
    pnu,
    postal_code,
    prescription,
    rrn,
    url,
    vehicle,
)

DETECTORS = (
    rrn.detect,
    frn.detect,
    business_reg.detect,
    corp_reg.detect,
    driver_license.detect,
    passport.detect,
    card.detect,
    medical_insurance.detect,
    prescription.detect,
    pnu.detect,
    fax.detect,
    phone.detect,
    email.detect,
    postal_code.detect,
    ip.detect,
    vehicle.detect,
    url.detect,
    address.detect,
    nationality.detect,
    account.detect,
    person.detect,
    # 식의약·법조 도메인
    edi_drug.detect,
    court_case.detect,
    # 인적 속성 (준식별자) — 학력·전공·직책·측정치 + 생년월일
    birth.detect,
    personal_attr.detect,
    # Domain-specific
    _dom_gov.detect,
    _dom_petition.detect,
    _dom_hr.detect,
)


def detect_all(
    text: str,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    *,
    normalize: bool = True,
) -> list[DetectionResult]:
    """Run every detector and return a merged, conflict-resolved list.

    Overlapping spans are resolved by (a) higher risk level, then (b) longer
    span, then (c) earlier start. This matches the design decisions D-002 /
    See CHANGELOG.md decision log (D-002 / D-003 / D-006 / D-008).

    ``include`` / ``exclude`` filter on the resulting DetectionResult labels.

    ``normalize`` (기본 True): 전각/호환문자 폴딩 + 제로폭 문자 제거로 검출
    우회를 차단한다. 결과 offset 은 원본 ``text`` 기준으로 역매핑된다.
    ASCII 입력은 우회 벡터가 없어 그대로 통과한다.
    """
    source = text
    offset_map: Optional[list[int]] = None
    if normalize and not text.isascii():
        norm, omap = normalize_unicode(text)
        if norm != text:
            text, offset_map = norm, omap

    raw: list[DetectionResult] = []
    for fn in DETECTORS:
        raw.extend(fn(text))

    inc = set(include) if include else None
    exc = set(exclude) if exclude else set()
    if inc is not None:
        raw = [d for d in raw if d.label in inc]
    if exc:
        raw = [d for d in raw if d.label not in exc]

    resolved = _resolve_overlaps(raw)
    if offset_map is not None:
        resolved = remap_to_source(resolved, offset_map, source)
    return resolved


def _resolve_overlaps(
    detections: Iterable[DetectionResult],
) -> list[DetectionResult]:
    """Deterministic overlap resolution.

    Sort by (start asc, -risk_level, -length, -confidence). Then sweep:
    a later detection that *starts inside* an already-accepted one is dropped.
    """
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
