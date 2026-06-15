"""Microsoft Presidio 비교 평가 — ko-pii vs Presidio (out-of-the-box + KR 보강).

이 모듈은 `model_comparison.HFPrivacyDetector` 와 같은 ``detect(text) -> list[Span]``
인터페이스를 노출하여 기존 평가 파이프라인 (``score_corpus`` + ``GoldDocument``)
에 그대로 끼울 수 있게 한다.

두 가지 변형:
  1. ``mode="default"`` — Presidio 기본 16 recognizer + ko_core_news_sm
     (Presidio 사용자가 ``pip install`` 후 한 줄로 얻는 것)
  2. ``mode="kr_adapt"`` — 위에 한국 핵심 PII 정규식 인식기 (RRN/FRN/PHONE/
     VEHICLE/BUSINESS_REG/DRIVER_LICENSE) 를 추가.  Presidio 사용자가 한국어
     지원을 위해 *최소한* 추가할 만한 수준의 보강 — ko-pii 의 100+ 룰/사전을
     복제하는 게 아니라 *정규식 1줄짜리* 만.

라벨 매핑 (Presidio → ko-pii):
    EMAIL_ADDRESS  → EMAIL
    PHONE_NUMBER   → PHONE
    URL            → URL
    IP_ADDRESS     → IP
    PERSON         → PERSON
    LOCATION       → ADDRESS  (rough — Presidio LOCATION 은 city/country 포함)
    DATE_TIME      → DT_BIRTH (rough — openai 와 동일한 limitation)
    KR_RRN         → RRN
    KR_FRN         → FRN
    KR_VEHICLE     → VEHICLE
    KR_BUSINESS    → BUSINESS_REG
    KR_DRIVER_LIC  → DRIVER_LICENSE
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ko_pii.core.types import DetectionResult


PRESIDIO_TO_KPII: dict[str, str] = {
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "URL": "URL",
    "IP_ADDRESS": "IP",
    "PERSON": "PERSON",
    "LOCATION": "ADDRESS",
    "DATE_TIME": "DT_BIRTH",
    # KR custom (kr_adapt mode 만)
    "KR_RRN": "RRN",
    "KR_FRN": "FRN",
    "KR_PHONE": "PHONE",
    "KR_VEHICLE": "VEHICLE",
    "KR_BUSINESS_REG": "BUSINESS_REG",
    "KR_DRIVER_LICENSE": "DRIVER_LICENSE",
    "KR_CARD": "CARD",
}


@dataclass
class Span:
    start: int
    end: int
    label: str
    text: str


# 한국 핵심 PII 정규식 인식기 (kr_adapt 모드)
# - RRN/FRN: 13자리 + 하이픈 (gender 자릿수로 RRN vs FRN 구분)
# - PHONE: 010/02/03x/+82
# - VEHICLE: 신형 NN가NNNN, NNN가NNNN
# - BUSINESS_REG: 3-2-5 사업자번호
# - DRIVER_LICENSE: 2-2-6-2
_KR_PATTERNS: list[tuple[str, str, float]] = [
    # label, regex, score
    ("KR_RRN_FRN_CANDIDATE", r"\d{6}-[1-8]\d{6}", 0.85),  # 후처리로 RRN/FRN 구분
    ("KR_PHONE", r"01[016789]-?\d{3,4}-?\d{4}", 0.9),
    ("KR_PHONE", r"0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])-?\d{3,4}-?\d{4}", 0.85),
    ("KR_PHONE", r"\+82[\s-]?\d{1,2}[\s-]?\d{3,4}[\s-]?\d{4}", 0.9),
    ("KR_VEHICLE", r"\d{2,3}[가-힣]\d{4}", 0.85),
    ("KR_BUSINESS_REG", r"\d{3}-\d{2}-\d{5}", 0.8),
    ("KR_DRIVER_LICENSE", r"(?:1[1-9]|2[0-8])-\d{2}-\d{6}-\d{2}", 0.85),
    ("KR_CARD", r"\b(?:\d{4}[\s-]?){3}\d{4}\b", 0.75),
]


def _make_kr_recognizers() -> list[Any]:
    """Create Presidio PatternRecognizer instances for KR_* labels."""
    from presidio_analyzer import Pattern, PatternRecognizer

    recognizers: list[Any] = []
    for label, regex, score in _KR_PATTERNS:
        rec = PatternRecognizer(
            supported_entity=label,
            patterns=[Pattern(name=f"{label}_regex", regex=regex, score=score)],
            supported_language="ko",
        )
        recognizers.append(rec)
    return recognizers


class PresidioDetector:
    """Presidio 분석기 wrapper.

    Parameters
    ----------
    mode : "default" | "kr_adapt"
        default — 기본 16 recognizer + spaCy 한국어
        kr_adapt — 위 + 한국 핵심 PII 6개 정규식 인식기
    spacy_model : str
        spaCy 한국어 모델 이름. 기본 ``ko_core_news_sm``.
    """

    def __init__(
        self,
        *,
        mode: str = "default",
        spacy_model: str = "ko_core_news_sm",
        min_score: float = 0.0,
    ) -> None:
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        if mode not in ("default", "kr_adapt"):
            raise ValueError(f"unknown mode: {mode}")
        self.mode = mode
        self.min_score = min_score

        nlp_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "ko", "model_name": spacy_model}],
        }
        provider = NlpEngineProvider(nlp_configuration=nlp_config)
        nlp = provider.create_engine()
        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp,
            supported_languages=["ko"],
        )

        if mode == "kr_adapt":
            for rec in _make_kr_recognizers():
                self.analyzer.registry.add_recognizer(rec)

    def detect(self, text: str) -> list[Span]:
        """Run Presidio analyzer and return Spans."""
        results = self.analyzer.analyze(text=text, language="ko")
        spans: list[Span] = []
        for r in results:
            if r.score < self.min_score:
                continue
            label = r.entity_type
            # RRN vs FRN 후처리 (gender digit 으로 구분)
            if label == "KR_RRN_FRN_CANDIDATE":
                # text[start..end] = 6자리-7자리, gender 는 7번째 (= dash 다음)
                snippet = text[r.start:r.end]
                m = re.match(r"\d{6}-(\d)", snippet)
                if m:
                    g = m.group(1)
                    label = "KR_FRN" if g in ("5", "6", "7", "8") else "KR_RRN"
                else:
                    continue
            spans.append(Span(start=r.start, end=r.end, label=label, text=text[r.start:r.end]))
        # Presidio recognizers may overlap (e.g., PERSON + LOCATION on same span);
        # drop overlapping lower-score duplicates.  Keep longest first, then highest
        # score.  This mimics what most Presidio users do via custom de-dup.
        spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
        deduped: list[Span] = []
        for s in spans:
            if deduped and s.start < deduped[-1].end:
                continue  # overlap — skip
            deduped.append(s)
        return deduped


def make_presidio_predict(
    detector: PresidioDetector,
) -> Callable[[str], list[DetectionResult]]:
    """Adapter — Presidio Spans → DetectionResult 리스트 (ko-pii eval 인터페이스).

    매핑되지 않는 라벨은 drop.  ko-pii 의 ``RiskLevel.MEDIUM`` / confidence 0.8 로
    표준화 (실제 점수는 detector 가 매김).
    """
    from ko_pii.core.types import DetectionResult, RiskLevel

    def predict(text: str) -> list[DetectionResult]:
        out: list[DetectionResult] = []
        for s in detector.detect(text):
            mapped = PRESIDIO_TO_KPII.get(s.label)
            if not mapped:
                continue
            out.append(DetectionResult(
                label=mapped,
                text=s.text.strip() if s.text else "",
                start=s.start,
                end=s.end,
                risk_level=RiskLevel.MEDIUM,
                confidence=0.8,
            ))
        return out

    return predict
