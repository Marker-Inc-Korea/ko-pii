"""Value-free comparison of two local core policies, with fresh in-memory Vaults."""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

from ko_pii.anonymizer import Anonymizer, AnonymizationResult
from ko_pii.core.modes import ProcessingMode
from ko_pii.eval.output import assess_output
from ko_pii.eval.synth import GoldDocument, GoldSpan
from ko_pii.io_.atomic import write_text_atomic
from ko_pii.labels import validate_label_filter
from ko_pii.patterns.person import normalize_exclusions
from ko_pii.policy import validate_strategies
from ko_pii.reporting.explanation import explain

_OPTIONS = {"mode", "strategy", "strategies", "include", "exclude", "person_exclusions"}


def _config(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        if not isinstance(value, Mapping) or not value.keys() <= _OPTIONS:
            raise ValueError
        mode = ProcessingMode(value.get("mode", "STRICT"))
        strategy = value.get("strategy", "tokenize")
        strategies = validate_strategies(strategy, value.get("strategies"))
        include = validate_label_filter(value.get("include"), name="include")
        exclude = validate_label_filter(value.get("exclude"), name="exclude")
        return {"mode": mode.value, "strategy": strategy, "strategies": strategies,
                "include": sorted(include) if include is not None else None,
                "exclude": sorted(exclude) if exclude else [],
                "person_exclusions": sorted(normalize_exclusions(value.get("person_exclusions")))}
    except (TypeError, ValueError):
        raise ValueError("invalid core policy; Vaults, model adapters and arbitrary options are not supported") from None


def _digest(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def compare_policies(text: str, *, before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    """Compare observable processing, not gold accuracy or whole-text safety.

    No caller-supplied Anonymizer, Vault or secondary detector is accepted. Only
    local core settings are allowed. No source/replacement values are returned.
    """
    if not isinstance(text, str) or len(text) > 100_000:
        raise ValueError("policy preview requires text of at most 100000 characters")
    configs = [_config(before), _config(after)]
    results = [Anonymizer(**{**config, "mode": ProcessingMode(config["mode"])}).process(text) for config in configs]
    spans = sorted({(r.detection.label, r.detection.start, r.detection.end)
                    for result in results for r in result.detections})
    if len(spans) > 2_000:
        raise ValueError("policy preview exceeds 2000 observed spans")
    observed = GoldDocument(text, [GoldSpan(label, start, end, text[start:end]) for label, start, end in spans])

    def states(result: AnonymizationResult) -> dict[tuple[str, int, int], dict[str, Any]]:
        records = {(r["label"], *r["source_span"]): r for r in explain(result)["findings"]}
        indexed = {}
        for row in assess_output(observed, result, result.summary["strategy"]):
            key = (row["label"], row["start"], row["end"])
            record = records.get(key)
            indexed[key] = {"detected": record is not None, "action": record["action"] if record else None,
                            "requested_strategy": record["requested_strategy"] if record else None,
                            "applied_strategy": record["applied_strategy"] if record else None,
                            "output_state": "not_detected" if row["state"] == "missed" else row["state"]}
        return indexed

    old, new = [states(result) for result in results]
    changes = [{"label": key[0], "source_span": [key[1], key[2]], "before": old[key], "after": new[key]}
               for key in spans if old[key] != new[key]]
    return {"schema_version": 1, "contract": "ko-pii-policy-preview-v1",
            "scope": "union_of_observed_spans_not_gold", "input_empty": not text,
            "offset_unit": "python_code_points", "whole_text_safety_assessed": False,
            "before_policy_sha256": _digest(configs[0]), "after_policy_sha256": _digest(configs[1]),
            "observed_span_count": len(spans), "changed_span_count": len(changes),
            "changed_by_label": dict(sorted(Counter(row["label"] for row in changes).items())),
            "before_output_counts": dict(sorted(Counter(row["output_state"] for row in old.values()).items())),
            "after_output_counts": dict(sorted(Counter(row["output_state"] for row in new.values()).items())),
            "changes": changes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview two core policies on a bounded UTF-8 text file.")
    parser.add_argument("input")
    parser.add_argument("--before", required=True, help="JSON policy settings")
    parser.add_argument("--after", required=True, help="JSON policy settings")
    parser.add_argument("--output", help="Value-free JSON report (default: stdout)")
    args = parser.parse_args(argv)
    try:
        if args.before == "-" or args.after == "-":
            raise ValueError("policy settings require distinct files, not stdin")
        if args.output:
            for source in (args.input, args.before, args.after):
                if (Path(source).resolve() == Path(args.output).resolve()
                        or os.path.exists(source) and os.path.exists(args.output) and os.path.samefile(source, args.output)):
                    raise ValueError("output must not overwrite source or configuration")
        from ko_pii.cli import _read_structured_input
        from ko_pii.io_.bounded import FileReadPolicy
        from ko_pii.structured import loads_json
        policy = FileReadPolicy(max_file_bytes=400_000, max_text_chars=100_000)
        text = _read_structured_input(args.input, policy)
        report = compare_policies(text, before=loads_json(_read_structured_input(args.before, policy)),
                                  after=loads_json(_read_structured_input(args.after, policy)))
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            write_text_atomic(args.output, output)
        else:
            sys.stdout.write(output)
        return 0
    except (ValueError, TypeError, OSError):
        sys.stderr.write("policy preview failed: check bounded UTF-8 input, core settings and distinct output path\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
