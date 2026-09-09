"""CLI — ko-pii input.txt --mode strict --vault vault.json --strategy tokenize.

표준 입력으로 받으려면 input 자리에 ``-`` 사용. 결과는 stdout 으로 (치환된 본문),
요약/검토는 stderr 로 출력한다. Vault 저장 경로가 지정되면 Vault JSON 도 함께 기록.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import TYPE_CHECKING, Any, Optional

from ko_pii import __version__
from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
from ko_pii.reporting.certificate import generate_certificate
from ko_pii.reporting.summary import format_summary_text
from ko_pii.vault.reversible import ReversibleVault

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
        default=ProcessingMode.STRICT.value,
        help="Processing mode (default: STRICT).",
    )
    p.add_argument(
        "-s", "--strategy",
        choices=["tokenize", "redact", "asterisk", "hashed", "partial", "fpe"],
        default="tokenize",
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
        default="cpu",
        help="Device for Privacy Filter (cpu/cuda/mps). Default: cpu.",
    )
    p.add_argument(
        "--merge-mode",
        choices=["union", "intersection", "cross_validation", "enrich_primary"],
        default="union",
        help="How to combine ko-pii with secondary detector (default: union).",
    )
    # 추가 입력 인자
    p.add_argument(
        "extra_inputs", nargs="*",
        help="Additional input paths/globs for --batch mode.",
    )
    return p


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    # 확장자 기반 자동 디스패처 (HWPX/DOCX/XLSX/CSV/TXT 등)
    from ko_pii.io_ import read_text
    return read_text(path)


def _write_output(path: Optional[str], text: str) -> None:
    if not path or path == "-":
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _split_csv(value: Optional[str]) -> Optional[list[str]]:
    if not value:
        return None
    return [t.strip() for t in value.split(",") if t.strip()]


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
    pw: Optional[str] = args.vault_password
    if pw == "__PROMPT__":          # 값 없는 --vault-password → 안전한 프롬프트 입력
        import getpass
        return getpass.getpass("Vault password: ")
    if pw:
        _emit_warning(
            args,
            "경고: --vault-password 값은 프로세스 목록/셸 히스토리에 노출됩니다. "
            "env var $KPII_VAULT_PASSWORD 또는 값 없는 --vault-password(프롬프트) 사용 권장.",
        )
        return pw
    return os.environ.get("KPII_VAULT_PASSWORD")


def _load_vault(args: argparse.Namespace) -> Optional[ReversibleVault]:
    """Open the vault — auto-detect encrypted format."""
    if not args.vault or not os.path.exists(args.vault):
        return None
    from ko_pii.vault.encrypted import is_encrypted_file, load_encrypted
    if is_encrypted_file(args.vault):
        pw = _resolve_vault_password(args)
        if not pw:
            raise SystemExit(
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
    if args.audit_log is not None:
        unsupported.append("--audit-log")
    if args.vault is not None:
        unsupported.append("--vault")
    if args.vault_password is not None:
        unsupported.append("--vault-password")
    if unsupported:
        parser.error(
            "--batch does not support "
            + ", ".join(unsupported)
            + "; process files individually when reversible Vault or audit records are required"
        )


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
            f"({type(exc).__name__}: {exc}).",
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
            f"계속합니다 ({type(exc).__name__}: {exc}).",
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
    try:
        secondary = None
        if args.with_privacy_filter:
            from ko_pii.integrations import get_privacy_filter_adapter
            secondary = get_privacy_filter_adapter(device=args.privacy_filter_device)

        anon = Anonymizer(
            mode=ProcessingMode(args.mode),
            strategy=args.strategy,
            vault=vault,
            include=_split_csv(args.include),
            exclude=_split_csv(args.exclude),
            secondary_detector=secondary,
            merge_mode=args.merge_mode,
            person_exclusions=_load_person_exclusions(args.person_exclusions_file),
        )
        if audit and anon.vault is not None:
            anon.vault.attach_audit(
                audit,
                failure_policy=args.audit_failure_policy,
            )

        result = anon.process(text)
        if audit:
            try:
                audit.record_anonymize(
                    count=len(result.detections),
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
    _close_audit(args, audit)

    _write_output(args.output, result.text)

    if args.vault and result.vault is not None:
        _save_vault(args, result.vault)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(generate_certificate(result, document_id=args.input))

    if args.json_summary:
        _write_json_summary(args, result.summary)
    else:
        sys.stderr.write(format_summary_text(result))
        sys.stderr.write("\n")

    return 0


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

    _validate_json_args(parser, args)

    if args.batch:
        _validate_batch_args(parser, args)
        return _run_batch(args)

    text = _read_input(args.input)
    vault = _load_vault(args)
    audit = _open_audit(args)
    return _run_single(args, text, vault, audit)


if __name__ == "__main__":
    raise SystemExit(main())
