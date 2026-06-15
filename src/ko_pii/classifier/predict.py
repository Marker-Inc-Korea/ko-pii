"""학습된 분류기 추론 (CPU 동작 보장).

사용:
    from ko_pii.classifier import PIIClassifier
    clf = PIIClassifier.from_pretrained("models/pii_classifier_v1/final")
    print(clf.predict("환경부 김도현 사무관 010-1234-5678"))  # → 1, 0.98
    print(clf.predict_batch(["문장1", "문장2"]))
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar, cast

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

_F = TypeVar("_F", bound=Callable[..., Any])

# torch.inference_mode 는 stub 없음(ignore_missing_imports) → Any.
# 데코레이터로서 시그니처를 보존하도록 명시 타입을 부여한다.
_inference_mode = cast(Callable[[], Callable[[_F], _F]], torch.inference_mode)


class PIIClassifier:
    """문서/청크 수준 has_pii 이진분류."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        max_length: int = 256,
        threshold: float = 0.5,
    ) -> None:
        self.model = model.eval()
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.threshold = threshold
        self.device = next(model.parameters()).device

    @classmethod
    def from_pretrained(cls, path: str | Path, **kwargs: Any) -> "PIIClassifier":
        try:
            tokenizer = AutoTokenizer.from_pretrained(str(path))
            model = AutoModelForSequenceClassification.from_pretrained(str(path))
        except (OSError, ValueError) as e:
            raise FileNotFoundError(
                f"분류기 모델을 '{path}' 에서 찾을 수 없습니다. 사전학습 가중치는 "
                "배포되지 않습니다(학습 데이터 라이선스) — "
                "`python -m ko_pii.classifier.train ...` 으로 직접 학습한 모델 "
                "디렉토리 경로를 지정하세요 (README '룰+ML 하이브리드' 절 참조)."
            ) from e
        return cls(model, tokenizer, **kwargs)

    @_inference_mode()
    def predict(self, text: str) -> tuple[int, float]:
        """단일 텍스트. 반환: (label 0/1, P(has_pii))."""
        return self.predict_batch([text])[0]

    @_inference_mode()
    def predict_batch(
        self, texts: Sequence[str], batch_size: int = 32
    ) -> list[tuple[int, float]]:
        out: list[tuple[int, float]] = []
        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            enc = self.tokenizer(
                batch,
                truncation=True,
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            logits = self.model(**enc).logits
            probs = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()
            for p in probs:
                out.append((int(p >= self.threshold), float(p)))
        return out

    def has_pii(self, text: str) -> bool:
        """편의 메서드 — 임계값 기반 boolean."""
        return self.predict(text)[0] == 1
