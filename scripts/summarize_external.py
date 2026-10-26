"""Generate a compact public result without source text or per-document spans."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def summarize(report: dict, full_sha256: str) -> dict:
    result = {key: report[key] for key in (
        "schema_version", "package_version", "generated_at", "evaluation_date",
        "dataset_sha256", "match_mode", "evaluated_labels", "document_count",
        "documents_with_misses", "micro", "per_label", "external_protocol",
        "protocol_sha256", "runner_sha256", "python", "adapter",
    )}
    result["summary_contract"] = "external-evaluation-summary-v1"
    result["full_report_sha256"] = full_sha256
    result["output_evaluation"] = {
        key: value for key, value in report["output_evaluation"].items() if key != "documents"
    }
    result["slices"] = report["slices"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    result = summarize(json.loads(raw), hashlib.sha256(raw).hexdigest())
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
