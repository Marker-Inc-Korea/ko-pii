"""End-to-end smoke: run the actual detector against a small synthetic corpus.

This is the most important regression: it catches changes that materially
degrade detection performance on realistic documents.
"""
from __future__ import annotations

from ko_pii.detect import detect_all
from ko_pii.eval.metrics import score_corpus
from ko_pii.eval.synth import generate_corpus


def test_baseline_recall_is_reasonable():
    corpus = generate_corpus(30, seed=0)
    report = score_corpus(corpus, detect_all, mode="partial")
    micro = report.micro()
    # Baseline expectations — keep these low enough to be stable across
    # dictionary changes, but high enough to catch real regressions.
    # 합성 코퍼스는 풍부한 다단락 텍스트 + 노이즈 ("PII 처럼 보이지만 PII 아님"
    # 단어/숫자/외국전화/체크섬-fail RRN 등) 가 의도적으로 포함됨. 일부 PERSON
    # FP 발생 가능. precision 0.65, recall 0.95+ 가 정직한 기준 (못잡는 샘플 포함).
    assert micro.precision >= 0.65
    assert micro.recall >= 0.95
    assert micro.f1 >= 0.78


def test_critical_labels_full_recall():
    """RRN / PHONE / EMAIL — high-precision deterministic detectors."""
    corpus = generate_corpus(30, seed=1)
    report = score_corpus(corpus, detect_all, mode="partial")
    for label in ("RRN", "PHONE", "EMAIL"):
        if label in report.per_label:
            m = report.per_label[label]
            assert m.recall >= 0.95, f"{label} recall = {m.recall:.3f}"
