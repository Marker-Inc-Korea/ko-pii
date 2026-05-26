"""CLI — ko-pii input.txt --mode strict --vault vault.json --strategy tokenize.

표준 입력으로 받으려면 input 자리에 ``-`` 사용. 결과는 stdout 으로 (치환된 본문),
요약/검토는 stderr 로 출력한다. Vault 저장 경로가 지정되면 Vault JSON 도 함께 기록.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from ko_pii import __version__
from ko_pii.anonymizer import Anonymizer
from ko_pii.core.modes import ProcessingMode
from ko_pii.reporting.certificate import generate_certificate
from ko_pii.reporting.summary import format_summary_text
from ko_pii.vault.reversible import ReversibleVault


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ko-pii",
        description="Rule-based PII detection and reversible pseudonymization "
                    "for Korean public-sector documents.",
    )
    p.add_argument("input", help="Input file path (or '-' for stdin).")
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
        help="Path to read/write the vault JSON (used by tokenize/hashed).",
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
        "--vault-password",
        help="Password for encrypted vault (use env var $KPII_VAULT_PASSWORD).",
    )
    p.add_argument(
        "--audit-log",
        help="Append audit log to this JSONL file.",
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


def _resolve_vault_password(args) -> Optional[str]:
    if args.vault_password:
        return args.vault_password
    return os.environ.get("KPII_VAULT_PASSWORD")


def _load_vault(args) -> Optional[ReversibleVault]:
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


def _save_vault(args, vault: ReversibleVault) -> None:
    if not args.vault:
        return
    pw = _resolve_vault_password(args)
    if pw:
        from ko_pii.vault.encrypted import save_encrypted
        save_encrypted(vault, args.vault, pw)
    else:
        vault.save(args.vault)


def _run_batch(args) -> int:
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
        progress=not args.no_progress,
    )
    sys.stderr.write(
        f"\n[배치 완료] 총 {summary.total_files}개 / 성공 {summary.succeeded} / "
        f"실패 {summary.failed} / 검출 {summary.total_detections} / "
        f"차단 {summary.total_blocked} / 검토 {summary.total_review} / "
        f"{summary.elapsed_s:.2f}초\n"
    )
    if args.json_summary:
        import dataclasses
        sys.stderr.write(json.dumps(
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
            ensure_ascii=False, indent=2,
        ))
        sys.stderr.write("\n")
    return 0 if summary.failed == 0 else 1


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.batch:
        return _run_batch(args)

    text = _read_input(args.input)

    vault = _load_vault(args)
    audit = None
    if args.audit_log:
        from ko_pii.vault.audit import AuditLog
        audit = AuditLog(args.audit_log)
        audit.__enter__()
        if vault is not None:
            vault.attach_audit(audit)

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
    )
    if audit and anon.vault is not None:
        anon.vault.attach_audit(audit)

    result = anon.process(text)
    _write_output(args.output, result.text)

    if args.vault and result.vault is not None:
        _save_vault(args, result.vault)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(generate_certificate(result, document_id=args.input))

    if audit:
        audit.record_anonymize(
            count=len(result.detections),
            mode=args.mode,
            context=args.input,
        )
        audit.__exit__(None, None, None)

    if args.json_summary:
        sys.stderr.write(json.dumps(result.summary, ensure_ascii=False, indent=2))
        sys.stderr.write("\n")
    else:
        sys.stderr.write(format_summary_text(result))
        sys.stderr.write("\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
