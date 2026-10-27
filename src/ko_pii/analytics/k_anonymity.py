"""k-익명성 (k-Anonymity) — 「비식별 조치 가이드라인」의 핵심 정량 지표.

정의:
- 데이터셋의 각 레코드가 *준식별자 조합* 이 동일한 다른 (k-1)개 레코드와
  구분되지 않을 때 k-익명성을 만족한다고 한다.
- 통상 k ≥ 5 권장. 민감속성이 포함된 데이터는 k ≥ 10.

본 모듈은 가명화된 레코드 집합 (각 레코드 = ``dict[label, value]``) 을 받아
- 준식별자 조합별 그룹 크기 계산
- 최소 그룹 크기 = k
- k < threshold 면 일반화 (generalization) 제안

원본 PII 가 아닌 *가명화 후* 레코드를 대상으로 평가하는 것이 표준 사용법.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from ko_pii.analytics.combined_risk import AttributeClass, classify_attribute


@dataclass
class KAnonymityReport:
    k: int                                  # min group size; 0 when not evaluated
    group_count: int
    smallest_group_size: int
    smallest_group_values: tuple[object, ...]
    quasi_identifier_keys: list[str]
    record_count: int
    satisfies_threshold: bool
    threshold: int = 5
    rationale: list[str] = field(default_factory=list)


def k_anonymity(
    records: Iterable[Mapping[str, object]],
    quasi_keys: list[str] | None = None,
    threshold: int = 5,
) -> KAnonymityReport:
    """``records`` 의 k-익명성을 평가.

    Parameters
    ----------
    records :
        각 레코드는 ``{label: value}`` 형태의 매핑. label 은
        :class:`AttributeClass` 분류와 일치하는 PII 카테고리.
    quasi_keys :
        준식별자로 간주할 키 목록. ``None`` 이면 ``classify_attribute`` 로
        ``QUASI_IDENTIFIER`` 인 것만 자동 선택. 선택한 열은 모든 행에 있어야 한다.
        키가 없으면 미평가(k=0, satisfies_threshold=False)를 반환한다.
    threshold :
        만족 기준 k 값 (양의 정수, 기본 5). 용도별 기준은 호출자가 결정한다.
    """
    if type(threshold) is not int or threshold < 1:
        raise ValueError("threshold must be a positive integer")
    if quasi_keys is not None:
        if (not isinstance(quasi_keys, list)
                or any(not isinstance(key, str) or not key for key in quasi_keys)
                or len(set(quasi_keys)) != len(quasi_keys)):
            raise ValueError("quasi_keys must be a list of distinct non-empty column names")
        quasi_keys = list(quasi_keys)
    record_list = [dict(r) for r in records]
    if not record_list:
        return KAnonymityReport(
            k=0, group_count=0, smallest_group_size=0,
            smallest_group_values=(),
            quasi_identifier_keys=[], record_count=0,
            satisfies_threshold=False, threshold=threshold,
            rationale=["빈 레코드"],
        )

    if quasi_keys is None:
        keys: set[str] = set()
        for rec in record_list:
            for k in rec.keys():
                if classify_attribute(k) == AttributeClass.QUASI_IDENTIFIER:
                    keys.add(k)
        quasi_keys = sorted(keys)

    if not quasi_keys:
        return KAnonymityReport(
            k=0,
            group_count=0,
            smallest_group_size=0,
            smallest_group_values=(),
            quasi_identifier_keys=[],
            record_count=len(record_list),
            satisfies_threshold=False,
            threshold=threshold,
            rationale=["준식별자가 없어 평가하지 않음; k=0은 미평가 표시"],
        )

    groups: dict[tuple[object, ...], int] = {}
    for rec in record_list:
        if any(k not in rec for k in quasi_keys):
            raise ValueError("quasi-identifier columns must be present in every record")
        key = tuple(rec[k] for k in quasi_keys)
        try:
            groups[key] = groups.get(key, 0) + 1
        except TypeError:
            raise ValueError("quasi-identifier values must be hashable") from None

    smallest_key, smallest_size = min(groups.items(), key=lambda kv: kv[1])
    rationale = [
        f"준식별자 {quasi_keys} 기준 {len(groups)}개 그룹",
        f"최소 그룹 크기 k = {smallest_size}",
    ]
    if smallest_size < threshold:
        rationale.append(
            f"k={smallest_size} < threshold {threshold} → 일반화 필요 "
            f"(권장: 연령 구간화, 주소 시·도 단위 등)"
        )
    else:
        rationale.append(f"k={smallest_size} ≥ {threshold} → 만족")

    return KAnonymityReport(
        k=smallest_size,
        group_count=len(groups),
        smallest_group_size=smallest_size,
        smallest_group_values=smallest_key,
        quasi_identifier_keys=quasi_keys,
        record_count=len(record_list),
        satisfies_threshold=smallest_size >= threshold,
        threshold=threshold,
        rationale=rationale,
    )


def evaluate_dataset(
    records: Iterable[Mapping[str, object]],
    threshold: int = 5,
) -> KAnonymityReport:
    """Convenience wrapper — auto-detects quasi-identifier keys."""
    return k_anonymity(records, quasi_keys=None, threshold=threshold)
