"""CLI — ko-pii input.txt --mode strict --vault vault.json --strategy tokenize.

표준 입력으로 받으려면 input 자리에 ``-`` 사용. 결과는 stdout 으로 (치환된 본문),
요약/검토는 stderr 로 출력한다. Vault 저장 경로가 지정되면 Vault JSON 도 함께 기록.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import math
import stat
from typing import TYPE_CHECKING, Any, Optional

from ko_pii import __version__
from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
from ko_pii.reporting.certificate import generate_certificate
from ko_pii.reporting.summary import format_summary_text
from ko_pii.vault.reversible import ReversibleVault
from ko_pii.io_.atomic import write_text_atomic
from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy
from ko_pii.io_.isolated import default_read_policy, read_text_isolated
from ko_pii.labels import validate_label_filter
from ko_pii.policy import validate_strategies

if TYPE_CHECKING:
    from ko_pii.vault.audit import AuditLog


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ko-pii",
        description="Rule-based PII detection and reversible pseudonymization "
                    "for Korean public-sector documents.",
    )
    p.add_argument("input", nargs="?",
                   help="Input file path (or '-' for stdin).")
    p.add_argument(
        "--labels",
        action="store_true",
        help="Print the 33 PII category labels (include/exclude keys) and exit.",
    )
    p.add_argument(
        "-m", "--mode",
        choices=[m.value for m in ProcessingMode],
        default=None,
        help="Processing mode (default: STRICT).",
    )
    p.add_argument(
        "-s", "--strategy",
        choices=["tokenize", "redact", "asterisk", "hashed", "partial", "fpe"],
        default=None,
        help="Substitution strategy (default: tokenize).",
    )
    p.add_argument(
        "--vault",
        help="Path to read/write the vault JSON (single-file mode only).",
    )
    p.add_argument(
        "--include",
        help="Comma-separated category labels to include (others ignored).",
    )
    p.add_argument(
        "--exclude",
        help="Comma-separated category labels to exclude.",
    )
    p.add_argument(
        "--person-exclusions-file",
        help="UTF-8 file with one domain term per line to exclude from PERSON detection.",
    )
    p.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout).",
    )
    p.add_argument(
        "--report",
        help="Write a processing certificate to this path.",
    )
    p.add_argument("--format", choices=["text", "json", "jsonl"], default="text",
                   help="Input/output format; JSON modes preserve keys and process values.")
    p.add_argument("--policy", help="Local versioned PolicyProfile JSON; cannot be combined with policy flags.")
    p.add_argument("--strategy-for", action="append", default=[], metavar="LABEL=STRATEGY",
                   help="Override a label's transformation (repeatable, single-file mode).")
    p.add_argument("--field-label", action="append", default=[], metavar="POINTER=LABEL",
                   help="Assert the label of an exact JSON Pointer (JSON modes only).")
    p.add_argument("--field-rules", help="JSON array of typed field rules; null path segments select array items.")
    p.add_argument("--field-person-exclusions", help="JSON object of exact field pointers to PERSON exclusion lists.")
    p.add_argument("--explain", help="Write value-free versioned JSON decision metadata.")
    p.add_argument("--trace-limit", type=int, default=0,
                   help="Opt-in overlap trace events per text/string field (0-1000); requires --explain.")
    p.add_argument("--report-include-sensitive", action="store_true",
                   help="Include raw review values, replacements and input path in --report. Do not share.")
    p.add_argument(
        "--json-summary",
        action="store_true",
        help="Print the summary as JSON to stderr instead of text.",
    )
    p.add_argument(
        "-V", "--version",
        action="version",
        version=f"ko-pii {__version__}",
    )
    # 배치 모드
    p.add_argument(
        "--batch",
        action="store_true",
        help="Treat input(s) as a directory or glob; process all matching files.",
    )
    p.add_argument(
        "--output-dir",
        help="Output directory for --batch mode (default: 'anon/').",
        default="anon",
    )
    p.add_argument(
        "--recursive", action="store_true", default=True,
        help="Recurse into subdirectories in --batch mode (default: True).",
    )
    p.add_argument(
        "--workers", type=int, default=1,
        help="Parallel workers for --batch mode (default: 1).",
    )
    p.add_argument(
        "--no-progress", action="store_true",
        help="Disable batch progress indicator.",
    )
    p.add_argument("--allow-empty", action="store_true",
                   help="Allow empty batch directories or unmatched globs (not missing explicit files).")
    # 암호화 vault
    p.add_argument(
        "--vault-password", nargs="?", const="__PROMPT__", default=None,
        help="Encrypted vault password. 값 없이 주면 프롬프트로 안전하게 입력. "
             "값을 직접 주면 프로세스 목록/히스토리에 노출되니 비권장 — "
             "env var $KPII_VAULT_PASSWORD 권장.",
    )
    p.add_argument(
        "--audit-log",
        help="Append audit log to this JSONL file (single-file mode only).",
    )
    p.add_argument(
        "--audit-failure-policy",
        choices=["raise", "best_effort"],
        default="raise",
        help="Behavior when audit logging fails (default: raise).",
    )
    # OpenAI Privacy Filter 통합 (옵션)
    p.add_argument(
        "--with-privacy-filter",
        action="store_true",
        help="Combine ko-pii with OpenAI Privacy Filter (ML, requires [ml] extras).",
    )
    p.add_argument(
        "--privacy-filter-device",
        default=None,
        help="Device for Privacy Filter (cpu/cuda/mps). Default: cpu.",
    )
    p.add_argument(
        "--merge-mode",
        choices=["union", "intersection", "cross_validation", "enrich_primary"],
        default=None,
        help="How to combine ko-pii with secondary detector (default: union).",
    )
    # 추가 입력 인자
    p.add_argument(
        "extra_inputs", nargs="*",
        help="Additional input paths/globs for --batch mode.",
    )
    limits = default_read_policy()
    p.add_argument("--max-file-bytes", type=int, default=limits.max_file_bytes)
    p.add_argument("--max-text-chars", type=int, default=limits.max_text_chars)
    p.add_argument("--max-decompressed-bytes", type=int, default=limits.max_decompressed_bytes)
    p.add_argument("--extraction-timeout", type=float, default=30.0,
                   help="Seconds allowed per file extraction (default: 30).")
    return p


def _read_input(path: str, policy: FileReadPolicy, timeout: float) -> tuple[str, dict[str, object] | None]:
    if path == "-":
        text = sys.stdin.read(min(policy.max_text_chars, policy.max_file_bytes) + 1)
        if len(text) > policy.max_text_chars or len(text.encode("utf-8")) > policy.max_file_bytes:
            raise BoundedReadError("stdin_too_large", "standard input exceeds configured limits")
        return text, None
    document = read_text_isolated(path, policy=policy, timeout=timeout)
    return document.text, document.coverage


def _write_output(path: Optional[str], text: str) -> None:
    if not path or path == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    write_text_atomic(path, text)


def _assignments(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        key, sep, value = item.rpartition("=")
        if not sep or not value or key in result:
            raise ValueError("assignments must be unique KEY=VALUE pairs")
        result[key] = value
    return result


def _read_structured_input(path: str, policy: FileReadPolicy) -> str:
    if path == "-":
        return _read_input(path, policy, 30.0)[0]
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > policy.max_file_bytes:
            raise ValueError("JSON input must be a bounded regular file")
        raw = handle.read(policy.max_file_bytes + 1)
    if len(raw) > policy.max_file_bytes:
        raise ValueError("JSON input exceeds byte limits")
    text = raw.decode("utf-8-sig")
    if len(text) > policy.max_text_chars:
        raise ValueError("JSON input exceeds character limits")
    return text


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    return [t.strip() for t in value.split(",")]


def _load_person_exclusions(path: Optional[str]) -> Optional[tuple[str, ...]]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return tuple(
            line
            for raw in f
            if (line := raw.strip()) and not line.startswith("#")
        )


def _emit_warning(args: argparse.Namespace, message: str) -> None:
    """Keep stderr machine-readable when ``--json-summary`` is active."""
    if getattr(args, "json_summary", False):
        warnings = getattr(args, "_json_warnings", None)
        if warnings is None:
            warnings = []
            setattr(args, "_json_warnings", warnings)
        if message not in warnings:
            warnings.append(message)
        return
    print(message, file=sys.stderr)


def _write_json_summary(
    args: argparse.Namespace,
    summary: dict[str, object],
) -> None:
    payload = dict(summary)
    warnings = getattr(args, "_json_warnings", [])
    if warnings:
        payload["warnings"] = list(warnings)
    sys.stderr.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stderr.write("\n")


def _resolve_vault_password(args: argparse.Namespace) -> Optional[str]:
    if hasattr(args, "_resolved_vault_password"):
        resolved: Optional[str] = args._resolved_vault_password
        return resolved
    pw: Optional[str] = args.vault_password
    if pw == "__PROMPT__":          # 값 없는 --vault-password → 안전한 프롬프트 입력
        import getpass
        pw = getpass.getpass("Vault password: ")
        if not pw:
            raise ValueError("Vault password must not be empty")
    elif pw:
        _emit_warning(
            args,
            "경고: --vault-password 값은 프로세스 목록/셸 히스토리에 노출됩니다. "
            "env var $KPII_VAULT_PASSWORD 또는 값 없는 --vault-password(프롬프트) 사용 권장.",
        )
    else:
        pw = os.environ.get("KPII_VAULT_PASSWORD")
    setattr(args, "_resolved_vault_password", pw)
    return pw


def _load_vault(args: argparse.Namespace) -> Optional[ReversibleVault]:
    """Open the vault — auto-detect encrypted format."""
    if not args.vault or not os.path.exists(args.vault):
        return None
    from ko_pii.vault.encrypted import is_encrypted_file, load_encrypted
    if is_encrypted_file(args.vault):
        pw = _resolve_vault_password(args)
        if not pw:
            raise ValueError(
                "암호화 vault: --vault-password 또는 환경변수 $KPII_VAULT_PASSWORD 필요."
            )
        return load_encrypted(args.vault, pw)
    return ReversibleVault.load(args.vault)


def _save_vault(args: argparse.Namespace, vault: ReversibleVault) -> None:
    if not args.vault:
        return
    pw = _resolve_vault_password(args)
    if pw:
        from ko_pii.vault.encrypted import save_encrypted
        save_encrypted(vault, args.vault, pw)
    else:
        _emit_warning(
            args,
            "경고: 암호 없이 저장한 Vault JSON에는 원본 개인정보가 평문으로 포함됩니다. "
            "운영 환경에서는 --vault-password 또는 KPII_VAULT_PASSWORD를 사용하십시오.",
        )
        vault.save(args.vault)


def _validate_batch_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    unsupported = []
    if (args.format != "text" or args.strategy_for or args.field_label or args.field_rules or args.field_person_exclusions
            or args.explain or args.report_include_sensitive):
        unsupported.append("structured/policy/explanation options")
    if args.audit_log is not None:
        unsupported.append("--audit-log")
    if args.vault is not None:
        unsupported.append("--vault")
    if args.vault_password is not None:
        unsupported.append("--vault-password")
    if args.with_privacy_filter:
        unsupported.append("--with-privacy-filter")
    if args.report is not None:
        unsupported.append("--report")
    if args.output is not None:
        unsupported.append("--output")
    if unsupported:
        parser.error(
            "--batch does not support "
            + ", ".join(unsupported)
            + "; use single-file mode for these options"
        )


def _validate_paths(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    paths = [("input", args.input)] if args.input != "-" else []
    for name in ("output", "vault", "report", "audit_log", "explain", "person_exclusions_file", "field_rules",
                 "field_person_exclusions", "policy"):
        value = getattr(args, name)
        if value is not None and not (name == "output" and value == "-"):
            if not value:
                parser.error(f"{name} path must not be empty")
            paths.append((name, value))
    for index, (name, value) in enumerate(paths):
        for other_name, other in paths[:index]:
            same = os.path.realpath(value) == os.path.realpath(other)
            if not same and os.path.exists(value) and os.path.exists(other):
                same = os.path.samefile(value, other)
            if same:
                parser.error(f"{name} and {other_name} must use different files")


def _validate_json_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.json_summary and args.vault_password == "__PROMPT__":
        parser.error(
            "--json-summary cannot use the interactive --vault-password prompt; "
            "set KPII_VAULT_PASSWORD instead"
        )


def _open_audit(args: argparse.Namespace) -> Optional["AuditLog"]:
    if not args.audit_log:
        return None

    from ko_pii.vault.audit import AuditLog

    audit = AuditLog(args.audit_log)
    try:
        return audit.__enter__()
    except Exception as exc:
        try:
            audit.__exit__(*sys.exc_info())
        except Exception:
            pass
        if args.audit_failure_policy == "raise":
            raise
        _emit_warning(
            args,
            "경고: 감사 로그를 열지 못해 감사 기록 없이 계속합니다 "
            f"({type(exc).__name__}).",
        )
        return None


def _close_audit(
    args: argparse.Namespace,
    audit: Optional["AuditLog"],
    active_error: Optional[tuple[Any, Any, Any]] = None,
) -> None:
    if audit is None:
        return
    try:
        audit.__exit__(*(active_error or (None, None, None)))
    except Exception as exc:
        # Preserve an in-flight processing error instead of hiding it with a
        # secondary close failure.
        if active_error is not None:
            return
        if args.audit_failure_policy == "raise":
            raise
        _emit_warning(
            args,
            "경고: 감사 로그를 정상적으로 종료하지 못했지만 best_effort 정책으로 "
            f"계속합니다 ({type(exc).__name__}).",
        )


def _run_batch(args: argparse.Namespace) -> int:
    from ko_pii.batch import process_paths
    inputs = [args.input] + (args.extra_inputs or [])
    summary = process_paths(
        inputs=inputs,
        output_dir=args.output_dir,
        mode=ProcessingMode(args.mode),
        strategy=args.strategy,
        recursive=args.recursive,
        workers=args.workers,
        include=_split_csv(args.include),
        exclude=_split_csv(args.exclude),
        person_exclusions=_load_person_exclusions(args.person_exclusions_file),
        progress=not args.no_progress and not args.json_summary,
        read_policy=args._read_policy,
        extraction_timeout=args.extraction_timeout,
        allow_empty=args.allow_empty,
    )
    if args.json_summary:
        import dataclasses
        _write_json_summary(
            args,
            {
                "total": summary.total_files,
                "succeeded": summary.succeeded,
                "failed": summary.failed,
                "detections": summary.total_detections,
                "blocked": summary.total_blocked,
                "review": summary.total_review,
                "elapsed_s": summary.elapsed_s,
                "results": [dataclasses.asdict(r) for r in summary.results],
                "skipped": summary.skipped,
            },
        )
    else:
        sys.stderr.write(
            f"\n[배치 완료] 총 {summary.total_files}개 / 성공 {summary.succeeded} / "
            f"실패 {summary.failed} / 검출 {summary.total_detections} / "
            f"차단 {summary.total_blocked} / 검토 {summary.total_review} / "
            f"{summary.elapsed_s:.2f}초\n"
        )
    return 0 if summary.failed == 0 else 1


def _run_single(
    args: argparse.Namespace,
    text: str,
    vault: Optional[ReversibleVault],
    audit: Optional["AuditLog"],
) -> int:
    args._stage = "processing"
    try:
        secondary = None
        if args.with_privacy_filter:
            from ko_pii.integrations import get_privacy_filter_adapter
            secondary = get_privacy_filter_adapter(device=args.privacy_filter_device)

        anon = args._profile.make_anonymizer(vault=vault, trace_limit=args.trace_limit) if args._profile else Anonymizer(
            mode=ProcessingMode(args.mode),
            strategy=args.strategy,
            vault=vault,
            include=_split_csv(args.include),
            exclude=_split_csv(args.exclude),
            secondary_detector=secondary,
            merge_mode=args.merge_mode,
            person_exclusions=_load_person_exclusions(args.person_exclusions_file),
            strategies=args._strategies,
            trace_limit=args.trace_limit,
        )
        if audit and anon.vault is not None:
            anon.vault.attach_audit(
                audit,
                failure_policy=args.audit_failure_policy,
            )

        explanation = None
        if args.format == "text":
            from ko_pii.reporting.explanation import explain
            result = anon.process(text)
            output_text = result.text
            active_vault = result.vault
            summary = dict(result.summary)
            detection_count = len(result.detections)
            if args.explain:
                explanation = explain(result, include_trace=bool(args.trace_limit))
        else:
            from ko_pii.structured import StructuredLimits, anonymize_json, anonymize_jsonl, loads_json
            limits = StructuredLimits(max_chars=args.max_text_chars)
            if args.format == "json":
                documents = [anonymize_json(loads_json(text, limits=limits), anonymizer=anon,
                                            field_labels=args._field_labels, limits=limits, field_rules=args._field_rules,
                                            field_person_exclusions=args._field_person_exclusions)]
                output_text = json.dumps(documents[0].data, ensure_ascii=False, indent=2) + "\n"
            else:
                documents = anonymize_jsonl(text, anonymizer=anon, field_labels=args._field_labels,
                                           limits=limits, field_rules=args._field_rules,
                                           field_person_exclusions=args._field_person_exclusions)
                output_text = "".join(json.dumps(doc.data, ensure_ascii=False) + "\n" for doc in documents)
            detection_count = sum(len(f.result.detections) for doc in documents for f in doc.fields)
            active_vault = anon.vault if ({anon.strategy, *anon.strategies.values()}
                                          & {"tokenize", "hashed", "fpe"}) else None
            summary = {"format": args.format, "documents": len(documents), "total": detection_count,
                       "keys_screened": False, "strategy": anon.strategy, "strategies": dict(anon.strategies),
                       "field_rules": [{"source_line": doc.source_line, "rules": doc.field_rule_summary}
                                       for doc in documents]}
            if args.explain:
                explanation = {"schema_version": 1,
                               "documents": [doc.report(include_trace=bool(args.trace_limit)) for doc in documents]}
        if audit:
            try:
                audit.record_anonymize(
                    count=detection_count,
                    mode=args.mode,
                    status="prepared",
                    context=args.input,
                )
            except Exception:
                if args.audit_failure_policy == "raise":
                    raise
                _emit_warning(
                    args,
                    "경고: 익명화 결과 준비 감사 레코드를 기록하지 못했습니다.",
                )
    except BaseException:
        _close_audit(args, audit, sys.exc_info())
        raise

    # Audit finalization belongs to the fail-closed boundary. The event above
    # says "prepared", not "persisted", because later filesystem/stdout writes
    # cannot be committed atomically with a JSONL audit file.
    args._stage = "audit_finalize"
    _close_audit(args, audit)

    if args.vault and active_vault is not None:
        args._stage = "vault_save"
        _save_vault(args, active_vault)
        args._vault_saved = True

    args._stage = "output_write"
    args._output_state = "uncertain"
    _write_output(args.output, output_text)
    args._output_state = "written"

    if args.report:
        args._stage = "report_write"
        certificate = generate_certificate(
            result, document_id=args.input,
            include_review_details=args.report_include_sensitive,
            include_document_id=args.report_include_sensitive,
            include_replacements=args.report_include_sensitive,
        )
        write_text_atomic(args.report, certificate)
    if args.explain and explanation is not None:
        args._stage = "explanation_write"
        write_text_atomic(args.explain, json.dumps(explanation, ensure_ascii=False, indent=2) + "\n")

    args._stage = "summary_write"
    if args.json_summary:
        if args._coverage is not None:
            summary["extraction_coverage"] = args._coverage
        _write_json_summary(args, summary)
    elif args.format == "text":
        sys.stderr.write(format_summary_text(result))
        sys.stderr.write("\n")
    else:
        sys.stderr.write(f"Processed {summary['documents']} document(s); {detection_count} detection(s). Keys not screened.\n")

    return 0


def _report_failure(args: argparse.Namespace, exc: Exception, *, code: str | None = None) -> int:
    stage = getattr(args, "_stage", "configuration")
    error = code or (exc.code if isinstance(exc, BoundedReadError) else f"{stage}_failed")
    message = str(exc) if isinstance(exc, BoundedReadError) else f"{stage} could not be completed"
    payload: dict[str, object] = {
        "status": "failed", "error": error, "stage": stage, "message": message,
        "vault_saved": getattr(args, "_vault_saved", False),
        "output_state": getattr(args, "_output_state", "not_written"),
    }
    if isinstance(exc, BoundedReadError) and exc.coverage is not None:
        payload["extraction_coverage"] = exc.coverage
    if args.json_summary:
        _write_json_summary(args, payload)
    else:
        print(f"ko-pii: {error}: {message}", file=sys.stderr)
    return 2 if stage == "configuration" else 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    setattr(args, "_json_warnings", [])

    if args.labels:
        from ko_pii.labels import format_labels_table
        print(format_labels_table())
        return 0
    if args.input is None:
        parser.error("input is required (or use --labels to list categories)")

    args._profile = None
    if args.policy is not None:
        if args.batch or args.policy == "-":
            parser.error("--policy requires a local settings file in single-file mode")
        if (any(getattr(args, name) is not None for name in (
                "mode", "strategy", "include", "exclude", "person_exclusions_file",
                "field_rules", "field_person_exclusions", "merge_mode", "privacy_filter_device"))
                or args.strategy_for or args.field_label or args.with_privacy_filter):
            parser.error("--policy cannot be combined with processing-policy or model flags")
    args.mode = args.mode if args.mode is not None else ProcessingMode.STRICT.value
    args.strategy = args.strategy if args.strategy is not None else "tokenize"
    args.merge_mode = args.merge_mode if args.merge_mode is not None else "union"
    args.privacy_filter_device = args.privacy_filter_device if args.privacy_filter_device is not None else "cpu"
    args._stage = "configuration"
    try:
        validate_label_filter(_split_csv(args.include), name="include")
        validate_label_filter(_split_csv(args.exclude), name="exclude")
        args._strategies = validate_strategies(args.strategy, _assignments(args.strategy_for))
        args._field_labels = _assignments(args.field_label)
    except ValueError as exc:
        return _report_failure(args, exc, code="invalid_label_filter" if not args.strategy_for and not args.field_label
                               else "invalid_processing_policy")
    if args.format == "text" and (args.field_label or args.field_rules or args.field_person_exclusions):
        parser.error("field options require --format json or jsonl")
    if not 0 <= args.trace_limit <= 1000 or (args.trace_limit and not args.explain):
        parser.error("--trace-limit requires --explain and must be between 0 and 1000")
    if args.format != "text" and (args.report or args.report_include_sensitive):
        parser.error("JSON modes use --explain instead of --report")
    if args.report_include_sensitive and not args.report:
        parser.error("--report-include-sensitive requires --report")
    _validate_json_args(parser, args)
    if args.vault_password == "":
        parser.error("--vault-password must not be empty")
    from dataclasses import replace
    try:
        args._read_policy = replace(
            default_read_policy(),
            max_file_bytes=args.max_file_bytes,
            max_text_chars=args.max_text_chars,
            max_decompressed_bytes=args.max_decompressed_bytes,
        )
        if not math.isfinite(args.extraction_timeout) or args.extraction_timeout <= 0:
            raise ValueError("extraction timeout must be finite and positive")
    except ValueError as exc:
        parser.error(str(exc))

    if args.batch:
        _validate_batch_args(parser, args)
        args._stage = "batch"
        try:
            return _run_batch(args)
        except (OSError, ValueError) as exc:
            return _report_failure(args, exc, code="batch_configuration")

    _validate_paths(parser, args)
    try:
        args._field_person_exclusions = None
        if args.field_person_exclusions:
            from ko_pii.structured import loads_json, _field_exclusions
            exclusions_config = loads_json(_read_structured_input(args.field_person_exclusions, args._read_policy))
            if not isinstance(exclusions_config, dict):
                raise ValueError("field person exclusions configuration must be a JSON object")
            args._field_person_exclusions = _field_exclusions(exclusions_config)
        args._field_rules = ()
        if args.field_rules:
            from ko_pii.field_rules import rules_from_json
            from ko_pii.structured import loads_json
            args._field_rules = rules_from_json(loads_json(_read_structured_input(args.field_rules, args._read_policy)))
        if args.policy:
            from ko_pii.profile import PolicyProfile
            args._profile = PolicyProfile.from_json(_read_structured_input(
                args.policy, FileReadPolicy(max_file_bytes=400_000, max_text_chars=100_000),
            ))
            if args.format == "text" and args._profile.structured:
                raise ValueError("profile field settings require --format json or jsonl")
            settings = args._profile.settings
            args.mode, args.strategy = settings["mode"], settings["strategy"]
            options = args._profile.structured_options()
            args._field_labels = options["field_labels"]
            args._field_rules = options["field_rules"]
            args._field_person_exclusions = options["field_person_exclusions"]
        args._stage = "extraction"
        if args.format == "text":
            text, args._coverage = _read_input(args.input, args._read_policy, args.extraction_timeout)
        else:
            text = _read_structured_input(args.input, args._read_policy)
            args._coverage = None
        args._stage = "vault_load"
        try:
            vault = _load_vault(args)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("invalid Vault structure") from exc
        args._stage = "audit_open"
        audit = _open_audit(args)
        return _run_single(args, text, vault, audit)
    except (OSError, ValueError, ImportError) as exc:
        return _report_failure(args, exc)


if __name__ == "__main__":
    raise SystemExit(main())
