"""OpenAI Privacy Filter 어댑터.

External: ``openai/privacy-filter`` (Apache-2.0, 2026-04-22)
Source: https://huggingface.co/openai/privacy-filter

특성:
- 1.5B params (MoE, active 50M)
- 128K context window
- 토큰 분류 (단일 forward pass)
- 다국어 지원 — *주력 영어*, 한국어/일본어 *성능 저하 가능*
- 로컬 실행 (GPU 추천, CPU 가능)

사용:
    from ko_pii.integrations import get_privacy_filter_adapter
    pf = get_privacy_filter_adapter(device="cpu")
    for det in pf.detect("홍길동 880101-1234568"):
        print(det.label, det.text)

설치:
    pip install ko-pii[ml]

본 어댑터는 *soft import* — transformers·torch 미설치 시 명시적 ``ImportError``
발생. ko-pii 코어는 본 모듈 import 안 함 (lazy via ``get_privacy_filter_adapter``).
"""
from __future__ import annotations

from typing import Iterator, Optional

from ko_pii.core.types import DetectionResult, RiskLevel


# Privacy Filter 네이티브 라벨 → ko-pii 라벨 매핑
# (label config 는 모델 카드 + Hugging Face hub 기준)
_LABEL_MAP: dict[str, Optional[str]] = {
    # 사람 / 이름
    "PERSON": "PERSON",
    "PER": "PERSON",
    "NAME": "PERSON",
    "PERSON_NAME": "PERSON",
    "FIRSTNAME": "PERSON",
    "LASTNAME": "PERSON",
    # 이메일
    "EMAIL_ADDRESS": "EMAIL",
    "EMAIL": "EMAIL",
    "E_MAIL": "EMAIL",
    # 전화
    "PHONE_NUMBER": "PHONE",
    "PHONE": "PHONE",
    "TELEPHONE": "PHONE",
    "MOBILE": "PHONE",
    # 주소
    "ADDRESS": "ADDRESS",
    "STREET_ADDRESS": "ADDRESS",
    "LOCATION": "ADDRESS",
    "LOC": "ADDRESS",
    # 금융
    "CREDIT_CARD": "CARD",
    "CREDIT_CARD_NUMBER": "CARD",
    "CARD_NUMBER": "CARD",
    "BANK_ACCOUNT": "ACCOUNT",
    "ACCOUNT_NUMBER": "ACCOUNT",
    # 식별번호
    "SSN": "RRN",   # 한국 RRN 과 가장 가까운 매핑
    "ID_CARD": "RRN",
    "NATIONAL_ID": "RRN",
    "PASSPORT": "PASSPORT",
    "PASSPORT_NUMBER": "PASSPORT",
    "DRIVER_LICENSE": "DRIVER_LICENSE",
    # 인터넷
    "URL": "URL",
    "IP_ADDRESS": "IP",
    "IP": "IP",
    # 조직 — 본 라이브러리에선 PII 아님 (도메인 사전에서 처리)
    "ORGANIZATION": None,
    "ORG": None,
    # 날짜·시간 — 본 라이브러리에선 미수집
    "DATE_TIME": None,
    "DATE": None,
    "TIME": None,
    # 직책 — 별도 라벨 (검출 안 함)
    "TITLE": None,
    # 일반
    "MISC": None,
    "O": None,         # outside tag
}


# 라벨별 위험도 (Privacy Filter 가 위험도 안 알려주므로 우리가 부여)
_RISK_LEVELS: dict[str, RiskLevel] = {
    "PERSON": RiskLevel.HIGH,
    "EMAIL": RiskLevel.MEDIUM,
    "PHONE": RiskLevel.MEDIUM,
    "ADDRESS": RiskLevel.MEDIUM,
    "CARD": RiskLevel.CRITICAL,
    "ACCOUNT": RiskLevel.HIGH,
    "RRN": RiskLevel.CRITICAL,
    "PASSPORT": RiskLevel.CRITICAL,
    "DRIVER_LICENSE": RiskLevel.HIGH,
    "URL": RiskLevel.INFO,
    "IP": RiskLevel.MEDIUM,
}


class OpenAIPrivacyFilterAdapter:
    """OpenAI Privacy Filter → ko-pii ``DetectionResult`` 변환 어댑터.

    Parameters
    ----------
    model_id : str
        Hugging Face model id (기본 ``openai/privacy-filter``).
    device : str
        ``"cpu"`` (기본), ``"cuda"``, ``"mps"`` 등.
    threshold : float
        토큰 확률 임계값. 이 미만은 무시 (기본 0.5).
    max_length : int
        한 번에 처리할 최대 토큰 수 (기본 4096, 모델 한계는 128K).
    """

    name = "openai-privacy-filter"

    def __init__(
        self,
        model_id: str = "openai/privacy-filter",
        device: str = "cpu",
        threshold: float = 0.5,
        max_length: int = 4096,
        label_map: Optional[dict[str, Optional[str]]] = None,
    ):
        self.model_id = model_id
        self.device = device
        self.threshold = threshold
        self.max_length = max_length
        self.label_map = label_map or _LABEL_MAP
        self._model = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import (  # type: ignore
                AutoModelForTokenClassification,
                AutoTokenizer,
            )
            import torch  # type: ignore  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "OpenAI Privacy Filter 어댑터는 transformers + torch 가 필요합니다.\n"
                "  pip install ko-pii[ml]\n"
                f"(원인: {e})"
            ) from e

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForTokenClassification.from_pretrained(self.model_id)
        self._model.to(self.device)
        self._model.eval()

    def detect(self, text: str) -> Iterator[DetectionResult]:
        """텍스트에서 PII 검출 — ko-pii 호환 ``DetectionResult`` yield."""
        if not text:
            return
        self._ensure_loaded()
        import torch

        # Tokenize with offset mapping (span 복원용)
        tok = self._tokenizer(
            text,
            return_tensors="pt",
            return_offsets_mapping=True,
            truncation=True,
            max_length=self.max_length,
        )
        offsets = tok.pop("offset_mapping")[0].tolist()
        inputs = {k: v.to(self.device) for k, v in tok.items()}

        with torch.no_grad():
            logits = self._model(**inputs).logits[0]
        probs = torch.softmax(logits, dim=-1)
        preds = probs.argmax(dim=-1).tolist()
        scores = probs.max(dim=-1).values.tolist()
        id2label = self._model.config.id2label

        # BIO-style span aggregation
        yield from self._bio_to_spans(
            text, offsets, preds, scores, id2label,
        )

    def _bio_to_spans(
        self,
        text: str,
        offsets: list[list[int]],
        preds: list[int],
        scores: list[float],
        id2label: dict[int, str],
    ) -> Iterator[DetectionResult]:
        current_label: Optional[str] = None
        current_start: int = -1
        current_end: int = -1
        current_confs: list[float] = []

        def flush() -> Optional[DetectionResult]:
            nonlocal current_label, current_start, current_end, current_confs
            if current_label is None:
                return None
            mapped = self.label_map.get(current_label)
            result: Optional[DetectionResult] = None
            if mapped and current_start >= 0 and current_end > current_start:
                conf = sum(current_confs) / max(1, len(current_confs))
                if conf >= self.threshold:
                    span_text = text[current_start:current_end]
                    if span_text.strip():
                        result = DetectionResult(
                            label=mapped,
                            text=span_text,
                            start=current_start,
                            end=current_end,
                            risk_level=_RISK_LEVELS.get(mapped, RiskLevel.MEDIUM),
                            confidence=conf,
                            evidence=[
                                f"source:{self.name}",
                                f"native_label:{current_label}",
                            ],
                            legal_basis=None,
                            extra={
                                "source": self.name,
                                "native_label": current_label,
                            },
                        )
            current_label = None
            current_start = -1
            current_end = -1
            current_confs = []
            return result

        for (start, end), p_idx, score in zip(offsets, preds, scores):
            label = id2label.get(p_idx, "O")
            # BIO 파싱: B-X / I-X / O
            if label.startswith("B-"):
                r = flush()
                if r:
                    yield r
                current_label = label[2:]
                current_start = start
                current_end = end
                current_confs = [score]
            elif label.startswith("I-") and current_label == label[2:]:
                current_end = end
                current_confs.append(score)
            elif label != "O" and not label.startswith(("B-", "I-")):
                # 일부 모델은 BIO 없이 직접 라벨 — 연속 처리
                if label == current_label:
                    current_end = end
                    current_confs.append(score)
                else:
                    r = flush()
                    if r:
                        yield r
                    current_label = label
                    current_start = start
                    current_end = end
                    current_confs = [score]
            else:  # "O" or boundary
                r = flush()
                if r:
                    yield r

        # flush 마지막
        r = flush()
        if r:
            yield r
