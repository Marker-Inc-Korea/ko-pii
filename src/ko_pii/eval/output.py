"""Assess labeled source spans against actual substitutions, without rescanning."""
from __future__ import annotations

from typing import Any

from ko_pii.anonymizer import AnonymizationResult
from ko_pii.eval.synth import GoldDocument

OUTPUT_STATES = (
    "replaced", "missed", "retained_by_policy", "partially_replaced",
    "partial_strategy", "literal_retained",
)


def assess_output(gold: GoldDocument, result: AnonymizationResult, strategy: str) -> list[dict[str, Any]]:
    """A replaced span is not proof of anonymity or of unannotated PII removal."""
    rows = []
    for span in gold.spans:
        applied = [s for s in result.substitutions if s.start < span.end and s.end > span.start]
        covered = sum(min(span.end, s.end) - max(span.start, s.start) for s in applied)
        if not applied:
            detected = any(r.detection.start < span.end and r.detection.end > span.start for r in result.detections)
            state = "retained_by_policy" if detected else "missed"
        elif covered < span.end - span.start:
            state = "partially_replaced"
        else:
            replacement = "".join(result.text[s.output_start:s.output_end] for s in applied)
            if gold.text[span.start:span.end] in replacement:
                state = "literal_retained"
            elif strategy == "partial":
                state = "partial_strategy"
            else:
                state = "replaced"
        rows.append({
            "label": span.label, "start": span.start, "end": span.end,
            "state": state, "covered_source_characters": covered,
        })
    return rows


def summarize_output(documents: list[dict[str, Any]], mode: str, strategy: str) -> dict[str, Any]:
    counts = dict.fromkeys(OUTPUT_STATES, 0)
    per_label: dict[str, dict[str, int]] = {}
    for document in documents:
        for span in document["spans"]:
            counts[span["state"]] += 1
            per_label.setdefault(span["label"], dict.fromkeys(OUTPUT_STATES, 0))[span["state"]] += 1
    return {
        "contract": "source-span-substitution-v1", "mode": mode, "strategy": strategy,
        "counts": counts, "per_label": per_label,
        "not_fully_replaced": sum(counts.values()) - counts["replaced"],
        "documents": documents,
    }
