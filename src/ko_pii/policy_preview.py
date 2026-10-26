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
from ko_pii.profile import CORE_OPTIONS as _OPTIONS, PolicyProfile, core_settings, structured_settings
from ko_pii.reporting.explanation import explain
from ko_pii.field_rules import rules_from_json
from ko_pii.structured import StructuredLimits, anonymize_json, _validate

_JSON_LIMITS = StructuredLimits(max_nodes=10_000, max_chars=100_000, max_string_chars=100_000)


def _config(value: Mapping[str, Any] | PolicyProfile) -> dict[str, Any]:
    return core_settings(value)


def _digest(config: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def compare_policies(text: str, *, before: Mapping[str, Any] | PolicyProfile,
                     after: Mapping[str, Any] | PolicyProfile) -> dict[str, Any]:
    """Compare observable processing, not gold accuracy or whole-text safety.

    No caller-supplied Anonymizer, Vault or secondary detector is accepted. Only
    local core settings are allowed. No source/replacement values are returned.
    """
    if not isinstance(text, str) or len(text) > 100_000:
        raise ValueError("policy preview requires text of at most 100000 characters")
    configs = [_config(before), _config(after)]
    results = [Anonymizer(**{**config, "mode": ProcessingMode(config["mode"])}).process(text) for config in configs]
    return {"schema_version": 1, "contract": "ko-pii-policy-preview-v1",
            "scope": "union_of_observed_spans_not_gold", "input_empty": not text,
            "offset_unit": "python_code_points", "whole_text_safety_assessed": False,
            "before_policy_sha256": _digest(configs[0]), "after_policy_sha256": _digest(configs[1]),
            **_compare_results(text, results)}


def _compare_results(text: str, results: list[AnonymizationResult]) -> dict[str, Any]:
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
    return {"observed_span_count": len(spans), "changed_span_count": len(changes),
            "changed_by_label": dict(sorted(Counter(row["label"] for row in changes).items())),
            "before_output_counts": dict(sorted(Counter(row["output_state"] for row in old.values()).items())),
            "after_output_counts": dict(sorted(Counter(row["output_state"] for row in new.values()).items())),
            "changes": changes}


def _structured_config(value: Mapping[str, Any] | PolicyProfile) -> dict[str, Any]:
    return structured_settings(value)


def compare_json_policies(
    data: Any, *, before: Mapping[str, Any] | PolicyProfile, after: Mapping[str, Any] | PolicyProfile,
    include_paths: bool = False,
) -> dict[str, Any]:
    """Compare a bounded JSON value using independent local core policies.

    Field rules use the JSON configuration form (null path segment = EACH).
    Raw values, replacements and keys are never returned by default. Explicit
    include_paths exposes JSON keys and is not suitable for public reports.
    """
    if type(include_paths) is not bool:
        raise ValueError("include_paths must be a boolean")
    _validate(data, {}, _JSON_LIMITS)
    configs = [_structured_config(before), _structured_config(after)]
    sources: list[tuple[str, str]] = []

    def collect(value: Any, path: str) -> None:
        if type(value) in (str, int):
            if len(sources) >= 1000:
                raise ValueError("structured policy preview exceeds 1000 string/integer fields")
            sources.append((path, str(value)))
        elif isinstance(value, dict):
            for key, child in value.items():
                collect(child, path + "/" + key.replace("~", "~0").replace("/", "~1"))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect(child, f"{path}/{index}")

    collect(data, "")
    processed = []
    for config in configs:
        anon = Anonymizer(**{**{k: v for k, v in config.items() if k in _OPTIONS},
                            "mode": ProcessingMode(config["mode"])})
        result = anonymize_json(data, anonymizer=anon, limits=_JSON_LIMITS,
                                field_labels=config["field_labels"],
                                field_rules=rules_from_json(config["field_rules"]),
                                field_person_exclusions=config["field_person_exclusions"])
        processed.append({field.path: field.result for field in result.fields})
    fields = []
    changes: list[dict[str, Any]] = []
    observed = 0
    old_counts: Counter[str] = Counter()
    new_counts: Counter[str] = Counter()
    for index, (path, text) in enumerate(sources):
        if not any(path in side for side in processed):
            continue  # Ordinary unasserted integers are not screened.
        results = [side.get(path) or AnonymizationResult(
            text, [], None, summary={"strategy": config["strategy"]},
        ) for config, side in zip(configs, processed)]
        comparison = _compare_results(text, results)
        observed += comparison["observed_span_count"]
        if observed > 2000:
            raise ValueError("structured policy preview exceeds 2000 observed spans")
        identity: dict[str, Any] = {"field_index": index}
        if include_paths:
            identity["path"] = path
        changes.extend({**identity, **change} for change in comparison.pop("changes"))
        fields.append({**identity, "before_screened": path in processed[0],
                       "after_screened": path in processed[1], **comparison})
        old_counts.update(comparison["before_output_counts"])
        new_counts.update(comparison["after_output_counts"])
    return {"schema_version": 1, "contract": "ko-pii-structured-policy-preview-v1",
            "scope": "union_of_observed_spans_not_gold", "whole_text_safety_assessed": False,
            "keys_screened": False, "unasserted_numbers_screened": False,
            "paths_included": include_paths, "offset_unit": "python_code_points_within_field",
            "field_index_scope": "string_and_integer_leaves_in_input_order",
            "before_policy_sha256": _digest(configs[0]), "after_policy_sha256": _digest(configs[1]),
            "compared_field_count": len(fields), "observed_span_count": observed,
            "changed_span_count": len(changes),
            "changed_by_label": dict(sorted(Counter(row["label"] for row in changes).items())),
            "before_output_counts": dict(sorted(old_counts.items())),
            "after_output_counts": dict(sorted(new_counts.items())),
            "fields": fields, "changes": changes}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview two core policies on bounded UTF-8 text or JSON.")
    parser.add_argument("input")
    parser.add_argument("--before", required=True, help="JSON policy settings")
    parser.add_argument("--after", required=True, help="JSON policy settings")
    parser.add_argument("--output", help="Value-free JSON report (default: stdout)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Input format; JSON enables field-specific policy settings.")
    parser.add_argument("--include-paths", action="store_true",
                        help="Include potentially sensitive JSON field paths (JSON mode only).")
    args = parser.parse_args(argv)
    if args.include_paths and args.format != "json":
        parser.error("--include-paths requires --format json")
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
        before = loads_json(_read_structured_input(args.before, policy))
        after = loads_json(_read_structured_input(args.after, policy))
        report = (compare_json_policies(loads_json(text, limits=_JSON_LIMITS), before=before, after=after,
                                        include_paths=args.include_paths) if args.format == "json"
                  else compare_policies(text, before=before, after=after))
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
