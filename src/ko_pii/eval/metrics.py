"""Precision / Recall / F1 — span-level + label-level.

매칭 정책:
- **strict**: 라벨 + (start, end) 가 정확히 일치해야 TP.
- **partial**: 라벨이 같고 span 이 겹치면 TP. (오프셋 1~2 자 차이 허용)

각 구간은 최대 한 번만 대응하며, partial은 순서와 무관한 최대 일대일 매칭을 쓴다.

기본 정책은 ``partial`` — 검출 모듈이 조사·구두점을 포함/배제하는 차이는
일상적이라서 strict 만 보면 점수가 과소평가됨.
"""
from __future__ import annotations

from collections.abc import Callable
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable

from ko_pii.core.types import DetectionResult
from ko_pii.eval.synth import GoldDocument, GoldSpan


@dataclass
class PerLabelMetrics:
    label: str
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r) / (p + r) if (p + r) else 0.0


@dataclass
class BenchmarkReport:
    per_label: dict[str, PerLabelMetrics] = field(default_factory=dict)
    document_count: int = 0
    match_mode: str = "partial"

    def micro(self) -> PerLabelMetrics:
        tp = sum(m.tp for m in self.per_label.values())
        fp = sum(m.fp for m in self.per_label.values())
        fn = sum(m.fn for m in self.per_label.values())
        return PerLabelMetrics(label="(micro)", tp=tp, fp=fp, fn=fn)

    def macro_f1(self) -> float:
        labels = list(self.per_label.values())
        if not labels:
            return 0.0
        return sum(m.f1 for m in labels) / len(labels)


def _spans_match(g: GoldSpan, p: DetectionResult, mode: str) -> bool:
    if g.label != p.label:
        return False
    if mode == "strict":
        return g.start == p.start and g.end == p.end
    # partial — non-empty overlap
    return g.start < p.end and p.start < g.end


def _validate_mode(mode: str) -> None:
    if mode not in ("strict", "partial"):
        raise ValueError("match mode must be 'strict' or 'partial'")


def _matching_size(edges: list[list[int]], prediction_count: int) -> int:
    """Maximum one-to-one matching using iterative augmenting paths."""
    owners = [-1] * prediction_count
    matches = [-1] * len(edges)
    count = 0
    for root in range(len(edges)):
        queue = deque([root])
        parents: dict[int, int] = {}
        free = -1
        while queue and free == -1:
            gold_index = queue.popleft()
            for prediction_index in edges[gold_index]:
                if prediction_index in parents:
                    continue
                parents[prediction_index] = gold_index
                owner = owners[prediction_index]
                if owner == -1:
                    free = prediction_index
                    break
                queue.append(owner)
        if free == -1:
            continue
        count += 1
        while free != -1:
            gold_index = parents[free]
            previous = matches[gold_index]
            matches[gold_index] = free
            owners[free] = gold_index
            free = previous
    return count


def score_document(
    gold: GoldDocument,
    predictions: Iterable[DetectionResult],
    mode: str = "partial",
) -> dict[str, PerLabelMetrics]:
    _validate_mode(mode)
    gold_by_label: dict[str, list[GoldSpan]] = {}
    pred_by_label: dict[str, list[DetectionResult]] = {}
    for g in gold.spans:
        gold_by_label.setdefault(g.label, []).append(g)
    for p in predictions:
        pred_by_label.setdefault(p.label, []).append(p)
    metrics: dict[str, PerLabelMetrics] = {}
    for label in sorted(gold_by_label.keys() | pred_by_label.keys()):
        gold_spans = gold_by_label.get(label, [])
        preds = pred_by_label.get(label, [])
        if mode == "strict":
            gold_counts = Counter((g.start, g.end) for g in gold_spans)
            pred_counts = Counter((p.start, p.end) for p in preds)
            tp = sum((gold_counts & pred_counts).values())
        else:
            edges = [[i for i, p in enumerate(preds) if _spans_match(g, p, mode)] for g in gold_spans]
            tp = _matching_size(edges, len(preds))
        metrics[label] = PerLabelMetrics(label=label, tp=tp, fp=len(preds) - tp, fn=len(gold_spans) - tp)
    return metrics


def score_corpus(
    gold_docs: Iterable[GoldDocument],
    predict_fn: Callable[[str], list[DetectionResult]],
    mode: str = "partial",
) -> BenchmarkReport:
    """Score a list of gold docs.

    ``predict_fn(text) -> list[DetectionResult]`` — the detector to evaluate.
    """
    _validate_mode(mode)
    report = BenchmarkReport(match_mode=mode)
    for doc in gold_docs:
        report.document_count += 1
        per_doc = score_document(doc, predict_fn(doc.text), mode=mode)
        for label, m in per_doc.items():
            agg = report.per_label.setdefault(
                label, PerLabelMetrics(label=label)
            )
            agg.tp += m.tp
            agg.fp += m.fp
            agg.fn += m.fn
    return report


def format_report(report: BenchmarkReport) -> str:
    lines: list[str] = []
    lines.append(f"문서 수: {report.document_count}")
    lines.append(f"매칭 정책: {report.match_mode}")
    lines.append("")
    lines.append(
        f"{'라벨':<22}{'정탐':>5}{'오탐':>5}{'미탐':>5}"
        f"{'정확도':>11}{'재현율':>9}{'F1':>8}"
    )
    lines.append("-" * 65)
    for label in sorted(report.per_label.keys()):
        m = report.per_label[label]
        lines.append(
            f"{label:<22}{m.tp:>5}{m.fp:>5}{m.fn:>5}"
            f"{m.precision:>10.3f} {m.recall:>8.3f}{m.f1:>8.3f}"
        )
    lines.append("-" * 65)
    micro = report.micro()
    lines.append(
        f"{'(전체)':<22}{micro.tp:>5}{micro.fp:>5}{micro.fn:>5}"
        f"{micro.precision:>10.3f} {micro.recall:>8.3f}{micro.f1:>8.3f}"
    )
    lines.append(f"{'(macro F1)':<22}{'':>15}{'':>11}{'':>9}{report.macro_f1():>8.3f}")
    return "\n".join(lines)
