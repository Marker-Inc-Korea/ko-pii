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
            elif any((r.strategy or strategy) == "partial" for r in result.detections
                     if any(s.start == r.detection.start and s.end == r.detection.end for s in applied)):
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


def compare_output_reports(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare actual retention states after corpus/annotation identity checks."""
    new, old = current.get("output_evaluation"), baseline.get("output_evaluation")
    if not isinstance(new, dict) or not isinstance(old, dict):
        raise ValueError("both reports require output evaluation")
    for key in ("contract", "mode", "strategy", "strategies"):
        if new.get(key, {}) != old.get(key, {}):
            raise ValueError("output policies differ; do not compare them as code regressions")

    def index(report: dict[str, Any]) -> dict[tuple[str, str, int, int], str]:
        rows = report.get("documents")
        if not isinstance(rows, list):
            raise ValueError("invalid output evaluation documents")
        result: dict[tuple[str, str, int, int], str] = {}
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or row["id"] in seen:
                raise ValueError("invalid output evaluation document")
            seen.add(row["id"])
            if not isinstance(row.get("spans"), list):
                raise ValueError("invalid output evaluation spans")
            for span in row["spans"]:
                if not isinstance(span, dict) or set(span) != {"label", "start", "end", "state", "covered_source_characters"}:
                    raise ValueError("invalid output evaluation span")
                if (not isinstance(span["label"], str) or type(span["start"]) is not int
                        or type(span["end"]) is not int or not 0 <= span["start"] < span["end"]
                        or span["state"] not in OUTPUT_STATES):
                    raise ValueError("invalid output evaluation state")
                key = (row["id"], span["label"], span["start"], span["end"])
                if key in result:
                    raise ValueError("duplicate output evaluation span")
                result[key] = span["state"]
        return result

    now, previous = index(new), index(old)
    expected = {(d["id"], s["label"], s["start"], s["end"])
                for d in current["documents"] for s in d["gold"]}
    if now.keys() != previous.keys() or now.keys() != expected:
        raise ValueError("output evaluation annotations differ")
    changes = [{"id": key[0], "label": key[1], "start": key[2], "end": key[3],
                "before": previous[key], "after": state}
               for key, state in sorted(now.items()) if state != previous[key]]
    return {"changes": changes,
            "new_not_fully_replaced": sum(row["before"] == "replaced" and row["after"] != "replaced" for row in changes),
            "resolved_not_fully_replaced": sum(row["before"] != "replaced" and row["after"] == "replaced" for row in changes)}
