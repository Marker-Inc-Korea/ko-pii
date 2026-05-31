"""학습된 분류기 추론 (CPU 동작 보장).

사용:
    from ko_pii.classifier import PIIClassifier
    clf = PIIClassifier.from_pretrained("models/pii_classifier_v1/final")
    print(clf.predict("환경부 김도현 사무관 010-1234-5678"))  # → 1, 0.98
    print(clf.predict_batch(["문장1", "문장2"]))
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class PIIClassifier:
    """문서/청크 수준 has_pii 이진분류."""

    def __init__(self, model, tokenizer, max_length: int = 256, threshold: float = 0.5):
        self.model = model.eval()
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.threshold = threshold
        self.device = next(model.parameters()).device

    @classmethod
    def from_pretrained(cls, path: str | Path, **kwargs) -> "PIIClassifier":
        tokenizer = AutoTokenizer.from_pretrained(str(path))
        model = AutoModelForSequenceClassification.from_pretrained(str(path))
        return cls(model, tokenizer, **kwargs)

    @torch.inference_mode()
    def predict(self, text: str) -> tuple[int, float]:
        """단일 텍스트. 반환: (label 0/1, P(has_pii))."""
        return self.predict_batch([text])[0]

    @torch.inference_mode()
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
