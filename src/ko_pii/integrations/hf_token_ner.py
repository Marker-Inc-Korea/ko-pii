"""HFTokenNERAdapter — ko-pii 라벨 스킴의 HF 토큰분류 NER 을 SecondaryDetector 로.

``docs/HYBRID_NER.md`` 의 레시피(``experiments/ner/code/train_ner.py``)로 학습한
토큰분류 모델(라벨이 ``B-PERSON``/``I-ADDRESS`` 처럼 ko-pii 카테고리명)을
:class:`ko_pii.Anonymizer` 의 ``secondary_detector`` 로 꽂는 어댑터.

하이브리드(외부 검증 F1 0.97) 사용 예::

    from ko_pii import Anonymizer
    from ko_pii.integrations.hf_token_ner import HFTokenNERAdapter

    ml = HFTokenNERAdapter("out/ner_fuzzy/final")   # 직접 학습한 모델 디렉토리
    anonymizer = Anonymizer(
        secondary_detector=ml,
        merge_mode="role_split",   # 룰=결정적 ID, ML=퍼지 (HYBRID_NER.md 구성)
    )
    result = anonymizer.process(text)

``[ml]`` extra (torch + transformers) 필요. 모델은 lazy 로드.
"""
from __future__ import annotations

from typing import Iterator, Optional

from ko_pii.core.types import DetectionResult, RiskLevel

#: ko-pii 룰 검출기와 동일한 위험도 매핑 (미지정 라벨은 MEDIUM)
_RISK_LEVELS: dict[str, RiskLevel] = {
    "RRN": RiskLevel.CRITICAL, "FRN": RiskLevel.CRITICAL,
    "PASSPORT": RiskLevel.CRITICAL, "DRIVER_LICENSE": RiskLevel.CRITICAL,
    "CARD": RiskLevel.HIGH, "ACCOUNT": RiskLevel.HIGH, "PHONE": RiskLevel.HIGH,
    "PERSON": RiskLevel.HIGH, "EMAIL": RiskLevel.HIGH,
    "ADDRESS": RiskLevel.MEDIUM,
}


def bio_decode(
    text: str,
    offsets: list[tuple[int, int]],
    tags: list[str],
    confidences: Optional[list[float]] = None,
    *,
    source: str = "hf-token-ner",
    min_person_len: int = 2,
) -> list[DetectionResult]:
    """BIO 태그 시퀀스 → DetectionResult 목록 (순수 함수 — torch 불필요).

    ``offsets[i]`` 는 토큰 i 의 (start, end) 문자 오프셋, ``tags[i]`` 는
    ``B-X``/``I-X``/``O``. 스페셜 토큰은 ``(0, 0)`` 오프셋으로 자동 무시.
    """
    confs = confidences or [1.0] * len(tags)
    out: list[DetectionResult] = []
    cur: Optional[tuple[str, int, int, list[float]]] = None  # (label, s, e, confs)

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        label, s, e, cs = cur
        cur = None
        span = text[s:e].strip()
        if not span or (label == "PERSON" and len(span) < min_person_len):
            return
        # strip 으로 잘린 만큼 오프셋 보정
        s += text[s:e].index(span)
        out.append(DetectionResult(
            label=label, text=span, start=s, end=s + len(span),
            risk_level=_RISK_LEVELS.get(label, RiskLevel.MEDIUM),
            confidence=sum(cs) / len(cs),
            evidence=[f"source:{source}", "method:token_classification"],
            legal_basis=None,
            extra={"source": source},
        ))

    for (s, e), tag, c in zip(offsets, tags, confs):
        if s == e:  # 스페셜 토큰
            continue
        if tag == "O":
            flush()
            continue
        pos, _, label = tag.partition("-")
        if pos == "B" or cur is None or cur[0] != label:
            flush()
            cur = (label, s, e, [c])
        else:
            cur = (label, cur[1], e, cur[3] + [c])
    flush()
    return out


class HFTokenNERAdapter:
    """ko-pii 라벨 스킴 HF 토큰분류 모델용 SecondaryDetector.

    Parameters
    ----------
    model_path :
        로컬 모델 디렉토리 또는 HF Hub id. ``config.id2label`` 의 엔티티명이
        ko-pii 카테고리(PERSON/ADDRESS/...)여야 한다 (HYBRID_NER 레시피 산출물이 이 형태).
    device :
        ``"cuda"``/``"cpu"``/None(자동 — cuda 가용 시 cuda).
    max_length :
        토크나이저 최대 길이 (기본 512).
    """

    def __init__(self, model_path: str, device: Optional[str] = None,
                 max_length: int = 512):
        self.name = f"hf-token-ner({model_path})"
        self.model_path = model_path
        self.device = device
        self.max_length = max_length
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModelForTokenClassification, AutoTokenizer
        except ImportError as e:  # pragma: no cover
            raise ImportError(
                "HFTokenNERAdapter 는 `pip install ko-pii[ml]` (torch+transformers) 필요"
            ) from e
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self._model = AutoModelForTokenClassification.from_pretrained(self.model_path)
        except (OSError, ValueError) as e:
            raise FileNotFoundError(
                f"토큰분류 NER 모델을 '{self.model_path}' 에서 찾을 수 없습니다. "
                "사전학습 가중치는 배포되지 않습니다(학습 데이터 라이선스 검토 중) — "
                "experiments/ner/code/train_ner.py 레시피로 직접 학습한 모델 디렉토리를 "
                "지정하세요 (docs/HYBRID_NER.md 재현 절 참조)."
            ) from e
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self.device).eval()

    def detect(self, text: str) -> Iterator[DetectionResult]:
        self._ensure_loaded()
        import torch
        enc = self._tokenizer(text, return_offsets_mapping=True, truncation=True,
                              max_length=self.max_length, return_tensors="pt")
        offsets = [tuple(o) for o in enc.pop("offset_mapping")[0].tolist()]
        with torch.no_grad():
            logits = self._model(**{k: v.to(self.device) for k, v in enc.items()}).logits[0]
        probs = logits.softmax(dim=-1)
        pred = probs.argmax(dim=-1).tolist()
        confs = probs.max(dim=-1).values.tolist()
        id2label = self._model.config.id2label
        tags = [id2label[p] for p in pred]
        yield from bio_decode(text, offsets, tags, confs, source=self.name)
