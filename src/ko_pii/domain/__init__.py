"""도메인 특화 룰 — 공문서·민원·인사 문서 양식별 추가 검출.

각 도메인 모듈은 ``Iterable[DetectionResult]`` 를 반환하는 ``detect(text)``
함수를 노출한다. 기본 ``detect_all`` 과 별개로 호출하거나, ``Anonymizer`` 의
미래 확장 훅으로 통합할 수 있다.
"""
from ko_pii.domain.government import detect as detect_government
from ko_pii.domain.civil_petition import detect as detect_civil_petition
from ko_pii.domain.hr import detect as detect_hr

__all__ = [
    "detect_government",
    "detect_civil_petition",
    "detect_hr",
]
