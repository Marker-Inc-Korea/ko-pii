"""Microsoft Presidio plugin — ko-pii 를 Presidio Recognizer 로 등록.

Presidio (https://github.com/microsoft/presidio) 는 Microsoft 의 가장 인기 OSS
PII 검출·가명화 프레임워크. 다만 *한국어 지원이 매우 약함*. 본 plugin 은
ko-pii 검출기를 Presidio EntityRecognizer 로 wrapping 하여, Presidio 사용자가
한 줄로 한국 공공 PII 인식 능력을 얻을 수 있게 함.

설치::

    pip install ko-pii[presidio]

사용::

    from presidio_analyzer import AnalyzerEngine
    from ko_pii.integrations.presidio_plugin import KPiiRecognizer

    analyzer = AnalyzerEngine()
    analyzer.registry.add_recognizer(KPiiRecognizer())

    results = analyzer.analyze(text="홍길동 880101-1234568", language="ko")

Presidio 가 한국어 nlp_engine 미설정이어도 본 recognizer 는 *룰 기반* 이라
독립 동작. spaCy 한국어 모델은 필요 없음.

엔티티 라벨 매핑:
    ko-pii         → Presidio 표준
    RRN           → KR_RRN (한국 특화 — Presidio 표준 SSN 과 별도)
    PHONE         → PHONE_NUMBER
    EMAIL         → EMAIL_ADDRESS
    CARD          → CREDIT_CARD
    ADDRESS       → KR_ADDRESS (한국 특화)
    PERSON        → PERSON
    ...
"""
from __future__ import annotations

from typing import Optional


# ko-pii → Presidio 표준 엔티티 라벨 매핑
# 한국 특화는 "KR_" prefix
_PRESIDIO_LABEL_MAP: dict[str, str] = {
    # 한국 고유 — KR_ prefix
    "RRN": "KR_RRN",
    "FRN": "KR_FRN",
    "BUSINESS_REG": "KR_BUSINESS_REG",
    "CORP_REG": "KR_CORP_REG",
    "DRIVER_LICENSE": "KR_DRIVER_LICENSE",
    "MEDICAL_INSURANCE": "KR_MEDICAL_INSURANCE",
    "PRESCRIPTION_ID": "KR_PRESCRIPTION_ID",
    "EDI_DRUG": "KR_EDI_DRUG",
    "VEHICLE": "KR_VEHICLE_PLATE",
    "POSTAL_CODE": "KR_POSTAL_CODE",
    "ADDRESS": "KR_ADDRESS",
    "ACCOUNT": "KR_BANK_ACCOUNT",
    "EMPLOYEE_ID": "KR_EMPLOYEE_ID",
    "DOC_ID": "KR_DOC_ID",
    "PETITION_ID": "KR_PETITION_ID",
    "COURT_CASE": "KR_COURT_CASE",
    "PNU": "KR_LAND_ID",
    # Presidio 표준 매핑
    "PASSPORT": "US_PASSPORT",   # Presidio 표준 PASSPORT 라벨
    "CARD": "CREDIT_CARD",
    "PHONE": "PHONE_NUMBER",
    "FAX": "PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS",
    "IP": "IP_ADDRESS",
    "URL": "URL",
    "PERSON": "PERSON",
}


def _get_supported_entities() -> list[str]:
    return sorted(set(_PRESIDIO_LABEL_MAP.values()))


try:
    from presidio_analyzer import EntityRecognizer, RecognizerResult  # type: ignore
    _HAS_PRESIDIO = True
except ImportError:
    _HAS_PRESIDIO = False


def _ensure_presidio() -> None:
    if not _HAS_PRESIDIO:
        raise ImportError(
            "ko-pii Presidio plugin 은 presidio-analyzer 가 필요합니다.\n"
            "  pip install ko-pii[presidio]\n"
            "또는 pip install presidio-analyzer presidio-anonymizer"
        )


if _HAS_PRESIDIO:

    class KPiiRecognizer(EntityRecognizer):
        """Presidio EntityRecognizer 어댑터 — ko-pii 검출 결과를 Presidio 포맷으로.

        Parameters
        ----------
        include : optional list[str]
            특정 ko-pii 라벨만 사용. None 이면 모든 검출기.
        exclude : optional list[str]
            제외할 ko-pii 라벨.
        supported_language : str
            기본 ``"ko"``. Presidio Analyzer 호출 시 language 일치해야 함.
        """

        def __init__(
            self,
            include: Optional[list[str]] = None,
            exclude: Optional[list[str]] = None,
            supported_language: str = "ko",
        ):
            self._include = include
            self._exclude = exclude
            self._label_map = _PRESIDIO_LABEL_MAP
            super().__init__(
                supported_entities=_get_supported_entities(),
                supported_language=supported_language,
                name="KPiiRecognizer",
            )

        def load(self) -> None:
            """No-op — ko-pii 는 정적 룰 기반이라 로드 작업 없음."""
            return None

        def analyze(self, text: str, entities, nlp_artifacts=None):
            """Presidio 가 호출하는 분석 함수.

            ``entities`` 는 요청된 엔티티 라벨 리스트 (예: ["KR_RRN"]). 본
            recognizer 가 지원하는 라벨만 필터링.
            """
            from ko_pii.detect import detect_all

            results = []
            wanted = set(entities) if entities else None

            for det in detect_all(
                text,
                include=self._include,
                exclude=self._exclude,
            ):
                presidio_label = self._label_map.get(det.label)
                if presidio_label is None:
                    continue
                if wanted is not None and presidio_label not in wanted:
                    continue

                results.append(
                    RecognizerResult(
                        entity_type=presidio_label,
                        start=det.start,
                        end=det.end,
                        score=float(det.confidence),
                        analysis_explanation=None,
                        recognition_metadata={
                            "ko_pii_label": det.label,
                            "ko_pii_risk_level": det.risk_level.name,
                            "ko_pii_legal_basis": det.legal_basis or "",
                            "ko_pii_evidence": list(det.evidence),
                        },
                    )
                )
            return results

else:
    # Stub for environments without presidio — call raises clear ImportError
    class KPiiRecognizer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            _ensure_presidio()
