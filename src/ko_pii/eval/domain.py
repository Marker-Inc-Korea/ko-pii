"""Evaluate labeled local documents and compare strict-span regressions."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from ko_pii import __version__
from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
from ko_pii.detect import detect_all
from ko_pii.eval.metrics import BenchmarkReport, PerLabelMetrics, score_document
from ko_pii.eval.synth import GoldDocument, GoldSpan
from ko_pii.eval.output import assess_output, summarize_output
from ko_pii.io_.atomic import write_text_atomic
from ko_pii.labels import ALL_LABELS
from ko_pii.patterns.person import normalize_exclusions

MAX_DATASET_BYTES = 16 * 1024 * 1024
MAX_DOCUMENTS = 10_000
MAX_DOCUMENT_CHARS = 100_000
MAX_SPANS = 2_000
REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LabeledDocument:
    id: str
    gold: GoldDocument


def _read_json_file(path: str | Path, max_bytes: int) -> str:
    with Path(path).open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("evaluation file exceeds the size limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("evaluation files must be UTF-8") from None


def _spans(
    value: Any, length: int, labels: set[str], *, max_spans: int = MAX_SPANS,
) -> set[tuple[str, int, int]]:
    if not isinstance(value, list) or len(value) > max_spans:
        raise ValueError("spans must be a bounded list")
    spans = set()
    for span in value:
        if not isinstance(span, dict) or set(span) != {"label", "start", "end"}:
            raise ValueError("each span requires exactly label, start and end")
        label, start, end = span["label"], span["start"], span["end"]
        if not isinstance(label, str) or label not in labels:
            raise ValueError("span label is outside the evaluated labels")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= length:
            raise ValueError("span offsets must be valid Python character offsets")
        key = (label, start, end)
        if key in spans:
            raise ValueError("duplicate span")
        spans.add(key)
    return spans


def load_dataset(path: str | Path) -> list[LabeledDocument]:
    """Load JSONL with id, text and a complete spans list for each document."""
    documents = []
    seen = set()
    for line_number, line in enumerate(_read_json_file(path, MAX_DATASET_BYTES).splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if not isinstance(item, dict) or set(item) != {"id", "text", "spans"}:
                raise ValueError("each document requires exactly id, text and spans")
            doc_id, text = item["id"], item["text"]
            if not isinstance(doc_id, str) or not doc_id.strip() or len(doc_id) > 128:
                raise ValueError("id must be a nonempty string of at most 128 characters")
            if doc_id in seen:
                raise ValueError("document ids must be unique")
            if not isinstance(text, str) or len(text) > MAX_DOCUMENT_CHARS:
                raise ValueError("text exceeds the document character limit")
            spans = _spans(item["spans"], len(text), set(ALL_LABELS))
            gold = GoldDocument(text, [
                GoldSpan(label, start, end, text[start:end]) for label, start, end in sorted(spans)
            ])
            documents.append(LabeledDocument(doc_id, gold))
            seen.add(doc_id)
            if len(documents) > MAX_DOCUMENTS:
                raise ValueError("dataset exceeds the document count limit")
        except (ValueError, TypeError, KeyError) as exc:
            # JSON decoder messages can contain source text; never echo the line.
            message = "invalid JSON" if isinstance(exc, json.JSONDecodeError) else str(exc)
            raise ValueError(f"dataset line {line_number}: {message}") from None
    if not documents:
        raise ValueError("dataset must contain at least one document")
    return documents


def _span_rows(spans: Iterable[tuple[str, int, int]]) -> list[dict[str, Any]]:
    return [{"label": label, "start": start, "end": end} for label, start, end in sorted(spans)]


def _counts(metric: PerLabelMetrics) -> dict[str, Any]:
    return {
        "tp": metric.tp, "fp": metric.fp, "fn": metric.fn,
        "precision": metric.precision if metric.tp + metric.fp else None,
        "recall": metric.recall if metric.tp + metric.fn else None,
        "f1": metric.f1 if metric.tp + metric.fp + metric.fn else None,
    }


def evaluate(
    documents: list[LabeledDocument],
    *,
    labels: Iterable[str] | None = None,
    person_exclusions: Iterable[str] = (),
    output_mode: ProcessingMode | None = None,
    output_strategy: str = "redact",
) -> dict[str, Any]:
    """Evaluate detection and optionally actual replacement of annotated spans."""
    if not documents:
        raise ValueError("dataset must contain at least one document")
    active = set(ALL_LABELS if labels is None else labels)
    if not active or not active <= set(ALL_LABELS):
        raise ValueError("evaluated labels must be a nonempty subset of ko-pii labels")
    exclusions = sorted(normalize_exclusions(person_exclusions))
    canonical = [{
        "id": doc.id, "text": doc.gold.text,
        "spans": _span_rows((s.label, s.start, s.end) for s in doc.gold.spans),
    } for doc in sorted(documents, key=lambda item: item.id)]
    dataset_hash = hashlib.sha256(json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    metrics = BenchmarkReport(match_mode="strict")
    rows = []
    output_rows = []
    for doc in sorted(documents, key=lambda item: item.id):
        gold = GoldDocument(doc.gold.text, [s for s in doc.gold.spans if s.label in active])
        if output_mode is not None:
            result = Anonymizer(
                mode=output_mode, strategy=output_strategy, include=active,
                person_exclusions=exclusions,
            ).process(doc.gold.text)
            predictions = [record.detection for record in result.detections]
            output_rows.append({"id": doc.id, "spans": assess_output(gold, result, output_strategy)})
        else:
            predictions = detect_all(doc.gold.text, include=active, person_exclusions=exclusions)
        per_label = score_document(gold, predictions, mode="strict")
        for label, score in per_label.items():
            total = metrics.per_label.setdefault(label, PerLabelMetrics(label))
            total.tp += score.tp
            total.fp += score.fp
            total.fn += score.fn
        expected = {(s.label, s.start, s.end) for s in gold.spans}
        predicted = {(p.label, p.start, p.end) for p in predictions}
        rows.append({
            "id": doc.id, "characters": len(doc.gold.text),
            "gold": _span_rows(expected), "predictions": _span_rows(predicted),
            "false_negatives": _span_rows(expected - predicted),
            "false_positives": _span_rows(predicted - expected),
        })
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "package_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": dataset_hash,
        "match_mode": "strict",
        "evaluated_labels": sorted(active),
        "person_exclusions_sha256": hashlib.sha256(json.dumps(exclusions).encode()).hexdigest(),
        "document_count": len(rows),
        "documents_with_misses": sum(bool(row["false_negatives"]) for row in rows),
        "micro": _counts(metrics.micro()),
        "per_label": {label: _counts(value) for label, value in sorted(metrics.per_label.items())},
        "documents": rows,
    }
    if output_mode is not None:
        report["output_evaluation"] = summarize_output(output_rows, output_mode.value, output_strategy)
    return report


def compare_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare spans on the same corpus, label scope and scoring contract."""
    for key in ("schema_version", "dataset_sha256", "match_mode", "evaluated_labels"):
        if key not in baseline or current[key] != baseline[key]:
            raise ValueError(f"baseline {key} differs; compare the same corpus and label scope")
    old_docs = baseline.get("documents")
    if not isinstance(old_docs, list) or len(old_docs) != len(current["documents"]):
        raise ValueError("baseline document set differs")
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in old_docs):
        raise ValueError("invalid baseline document")
    by_id = {row["id"]: row for row in old_docs}
    if len(by_id) != len(old_docs):
        raise ValueError("duplicate baseline document id")
    changes: dict[str, list[dict[str, Any]]] = {
        "new_false_negatives": [], "resolved_false_negatives": [],
        "new_false_positives": [], "resolved_false_positives": [],
    }
    active = set(current["evaluated_labels"])
    for row in current["documents"]:
        old = by_id.get(row["id"])
        if old is None or old.get("characters") != row["characters"] or old.get("gold") != row["gold"]:
            raise ValueError("baseline annotations differ")
        length = row["characters"]
        gold = _spans(row["gold"], length, active)
        previous = _spans(old.get("predictions"), length, active, max_spans=MAX_DOCUMENT_CHARS)
        predicted = _spans(row["predictions"], length, active, max_spans=MAX_DOCUMENT_CHARS)
        old_fn, new_fn = gold - previous, gold - predicted
        old_fp, new_fp = previous - gold, predicted - gold
        for key, spans in (
            ("new_false_negatives", new_fn - old_fn),
            ("resolved_false_negatives", old_fn - new_fn),
            ("new_false_positives", new_fp - old_fp),
            ("resolved_false_positives", old_fp - new_fp),
        ):
            changes[key].extend({"id": row["id"], **span} for span in _span_rows(spans))
    return {
        "baseline_version": baseline.get("package_version"),
        "scope": "detector_spans_only",
        "counts": {key: len(rows) for key, rows in changes.items()},
        **changes,
    }


def format_summary(report: dict[str, Any]) -> str:
    lines = [f"Documents: {report['document_count']} | matching: strict character spans",
             "Label                 TP     FP     FN   Precision  Recall"]
    for label, values in report["per_label"].items():
        p = "n/a" if values["precision"] is None else f"{values['precision']:.3f}"
        r = "n/a" if values["recall"] is None else f"{values['recall']:.3f}"
        lines.append(f"{label:<20} {values['tp']:>5} {values['fp']:>6} {values['fn']:>6} {p:>10} {r:>7}")
    lines.append(f"Documents with unmatched gold spans: {report['documents_with_misses']}")
    if "output_evaluation" in report:
        output = report["output_evaluation"]
        lines.append(f"Output evaluation: {output['mode']} / {output['strategy']} (annotated spans only)")
        lines.extend(f"{state}: {count}" for state, count in output["counts"].items())
    if "comparison" in report:
        lines.append("Baseline comparison: detector spans only (output retention is an absolute check)")
        for key, count in report["comparison"]["counts"].items():
            lines.append(f"{key}: {count}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ko-pii-evaluate",
        description="Evaluate labeled local JSONL documents and compare detector regressions.",
    )
    parser.add_argument("dataset", help="UTF-8 JSONL containing id, text and spans")
    parser.add_argument("--output", required=True, help="JSON report (no source text or span values)")
    parser.add_argument("--labels", help="Comma-separated labels; annotate all occurrences of these labels")
    parser.add_argument("--person-exclusions-file")
    parser.add_argument("--baseline", help="Earlier report for the same corpus and label scope")
    parser.add_argument("--fail-on-new-misses", action="store_true")
    parser.add_argument("--fail-on-new-false-positives", action="store_true")
    parser.add_argument("--output-mode", choices=[mode.value for mode in ProcessingMode])
    parser.add_argument("--output-strategy", choices=["redact", "tokenize", "asterisk", "partial", "hashed", "fpe"])
    parser.add_argument("--fail-on-retained", action="store_true",
                        help="Fail if any gold span is not fully replaced, including intentional partial masking")
    args = parser.parse_args(argv)
    if (args.fail_on_new_misses or args.fail_on_new_false_positives) and not args.baseline:
        parser.error("regression exit-code options require --baseline")
    if (args.fail_on_retained or args.output_strategy) and not args.output_mode:
        parser.error("output evaluation options require --output-mode")
    output = Path(args.output).resolve()
    for source in (args.dataset, args.baseline, args.person_exclusions_file):
        if source and (output == Path(source).resolve() or (
            output.exists() and Path(source).exists() and output.samefile(source)
        )):
            parser.error("output must not overwrite the dataset, baseline or exclusions")
    try:
        exclusions: tuple[str, ...] = ()
        if args.person_exclusions_file:
            exclusions = tuple(line.strip() for line in _read_json_file(
                args.person_exclusions_file, 1024 * 1024,
            ).splitlines() if line.strip() and not line.lstrip().startswith("#"))
        labels = None if args.labels is None else [s.strip() for s in args.labels.split(",")]
        report = evaluate(
            load_dataset(args.dataset), labels=labels, person_exclusions=exclusions,
            output_mode=ProcessingMode(args.output_mode) if args.output_mode else None,
            output_strategy=args.output_strategy or "redact",
        )
        if args.baseline:
            baseline = json.loads(_read_json_file(args.baseline, 64 * 1024 * 1024))
            if not isinstance(baseline, dict):
                raise ValueError("baseline must be a JSON object")
            report["comparison"] = compare_reports(report, baseline)
        serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if len(serialized.encode("utf-8")) > 64 * 1024 * 1024:
            raise ValueError("report exceeds 64 MiB; split the evaluation dataset")
        write_text_atomic(output, serialized)
    except (OSError, ValueError) as exc:
        # Paths may contain identifiers; filesystem exceptions are not echoed.
        message = "file could not be read or written" if isinstance(exc, OSError) else str(exc)
        print(f"ko-pii-evaluate: {message}", file=sys.stderr)
        return 2
    print(format_summary(report))
    counts = report.get("comparison", {}).get("counts", {})
    if args.fail_on_retained and report["output_evaluation"]["not_fully_replaced"]:
        return 1
    if args.fail_on_new_misses and counts.get("new_false_negatives", 0):
        return 1
    if args.fail_on_new_false_positives and counts.get("new_false_positives", 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
