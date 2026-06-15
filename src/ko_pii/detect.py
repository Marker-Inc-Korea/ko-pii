"""All-detector entry point — 모든 카테고리 검출기를 한 번에 실행."""
from __future__ import annotations

from typing import Iterable, Optional

from ko_pii.core.types import DetectionResult
from ko_pii.core.overlap import resolve_overlaps as _resolve_overlaps
from ko_pii.core.unicode_norm import (
    needs_normalization,
    normalize_unicode,
    remap_to_source,
)
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

    Overlapping spans are resolved by priority — higher risk level, then higher
    confidence, then longer span, then earlier start — so a lower-priority span
    never shadows a higher-confidence PII span (see ``_resolve_overlaps``).

    ``include`` / ``exclude`` filter on the resulting DetectionResult labels.

    ``normalize`` (기본 True): 전각/호환문자 폴딩 + 제로폭 문자 제거로 검출
    우회를 차단한다. 결과 offset 은 원본 ``text`` 기준으로 역매핑된다.
    ASCII 입력은 우회 벡터가 없어 그대로 통과한다.
    """
    if not isinstance(text, str):
        raise TypeError(f"detect_all() expects str, got {type(text).__name__}")
    source = text
    offset_map: Optional[list[int]] = None
    if normalize and needs_normalization(text):
        norm, omap = normalize_unicode(text)
        if norm != text:
            text, offset_map = norm, omap

    raw: list[DetectionResult] = []
    for fn in DETECTORS:
        raw.extend(fn(text))

    if offset_map is not None:
        # 정규화가 텍스트를 바꿨다(전각 폴딩/보이지 않는 문자 제거 등).
        # 정규화본 검출 offset 을 원본으로 역매핑한 뒤, **원본에도 검출을 한 번 더
        # 수행해 합집합**한다. 보이지 않는 문자(ZWSP·소프트하이픈 등) 제거가 인접
        # PII 두 개(예: RRN​전화)를 하나의 숫자열로 융합시켜 양쪽 검출기의 경계
        # 가드가 둘 다 거부하던 누출을 막는다 — 원본에서는 그 문자가 경계 역할을
        # 해 둘 다 검출된다. 정상 PII 중복은 아래 겹침 해소가 합쳐준다.
        raw = remap_to_source(raw, offset_map, source)
        for fn in DETECTORS:
            raw.extend(fn(source))

    inc = set(include) if include else None
    exc = set(exclude) if exclude else set()
    if inc is not None:
        raw = [d for d in raw if d.label in inc]
    if exc:
        raw = [d for d in raw if d.label not in exc]

    return _resolve_overlaps(raw)


# 겹침 해소는 core.overlap.resolve_overlaps 단일 구현 사용 (위 import 의 _resolve_overlaps).
# detect_all / merge_detections(integrations.hybrid) / 치환(modes._apply) 이 모두 같은
# 우선순위(위험도→확신도→길이)로 해소해 누출 회귀를 차단한다.
