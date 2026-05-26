"""평가 (Evaluation) — 합성 문서 + 라벨 + Precision/Recall/F1."""
from ko_pii.eval.synth import (
    GoldSpan,
    GoldDocument,
    generate_document,
    generate_corpus,
)
from ko_pii.eval.metrics import (
    PerLabelMetrics,
    BenchmarkReport,
    score_document,
    score_corpus,
    format_report,
)

__all__ = [
    "GoldSpan",
    "GoldDocument",
    "generate_document",
    "generate_corpus",
    "PerLabelMetrics",
    "BenchmarkReport",
    "score_document",
    "score_corpus",
    "format_report",
]
