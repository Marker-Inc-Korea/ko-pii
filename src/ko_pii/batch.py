"""배치 / 병렬 처리 — 디렉토리·glob 패턴 일괄 가명화.

특징:
- ``multiprocessing.Pool`` 로 워커 병렬화 (stdlib)
- 진행률 표시 (stderr 라인 갱신, 외부 deps 없이)
- 입력 파일별 결과를 *대응되는 출력 경로* 에 기록
- 파일마다 독립된 처리 상태 사용 (문서 간 Vault 일관성·감사 로그는 CLI 배치 미지원)
- 실패한 파일은 건너뛰고 보고 (전체 작업 중단 X)

Usage::

    from ko_pii.batch import process_paths
    results = process_paths(
        inputs=["docs/"],
        output_dir="out/",
        mode=ProcessingMode.STRICT,
        strategy="tokenize",
        recursive=True,
        workers=4,
    )
"""
from __future__ import annotations

import os
import math
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable, Optional

from ko_pii.core.modes import ProcessingMode
from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy
from ko_pii.io_.isolated import default_read_policy, read_text_isolated
from ko_pii.io_.atomic import write_text_atomic
from ko_pii.labels import validate_label_filter


@dataclass
class FileResult:
    input_path: str
    output_path: Optional[str]
    detections: int
    combined_risk: str
    blocked: int
    review: int
    error: Optional[str] = None
    elapsed_s: float = 0.0
    error_code: Optional[str] = None
    coverage: Optional[dict[str, object]] = None


@dataclass
class BatchSummary:
    total_files: int = 0
    succeeded: int = 0
    failed: int = 0
    total_detections: int = 0
    total_blocked: int = 0
    total_review: int = 0
    elapsed_s: float = 0.0
    results: list[FileResult] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────
# 파일 수집
# ─────────────────────────────────────────────────────────────────────

DEFAULT_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".md", ".log",
    ".csv", ".tsv",
    ".hwpx", ".hwp",
    ".docx", ".xlsx",
    ".pdf",
})


def collect_files(
    inputs: Iterable[str],
    recursive: bool = True,
    extensions: Optional[frozenset[str]] = None,
) -> list[str]:
    """입력 경로(파일·디렉토리·glob) 를 모두 풀어 파일 목록을 반환."""
    files, _, _ = _collect_inputs(inputs, recursive, extensions)
    return files


def _collect_inputs(
    inputs: Iterable[str],
    recursive: bool,
    extensions: Optional[frozenset[str]],
    *,
    output_root: Optional[str] = None,
    allow_empty: bool = False,
) -> tuple[list[str], list[FileResult], list[dict[str, str]]]:
    from glob import glob, has_magic

    exts = extensions if extensions is not None else DEFAULT_EXTENSIONS
    seen: set[str] = set()
    out: list[str] = []
    errors: list[FileResult] = []
    skipped: list[dict[str, str]] = []

    def fail(path: str, code: str) -> None:
        errors.append(FileResult(path, None, 0, "UNKNOWN", 0, 0, error=code, error_code=code))

    def excluded(path: str) -> bool:
        return output_root is not None and Path(os.path.realpath(path)).is_relative_to(output_root)

    def add(path: str, *, explicit: bool) -> int:
        if excluded(path):
            skipped.append({"input_path": path, "reason": "output_directory"})
            return 0
        if not os.path.isfile(path):
            fail(path, "file_unavailable")
            return 0
        if os.path.splitext(path)[1].lower() not in exts:
            if explicit:
                fail(path, "unsupported_extension")
            else:
                skipped.append({"input_path": path, "reason": "unsupported_extension"})
            return 0
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            out.append(path)
        return 1

    def visit(path: str) -> None:
        if excluded(path):
            skipped.append({"input_path": path, "reason": "output_directory"})
            return
        if not os.path.isdir(path):
            add(path, explicit=True)
            return
        count = 0
        before_errors = len(errors)

        def walk_error(error: OSError) -> None:
            fail(str(error.filename or path), "directory_unavailable")

        for root, dirs, names in os.walk(path, onerror=walk_error):
            for directory in dirs[:]:
                candidate = os.path.join(root, directory)
                if excluded(candidate) or os.path.islink(candidate):
                    dirs.remove(directory)
                    skipped.append({"input_path": candidate, "reason": "directory_not_traversed"})
            for name in names:
                count += add(os.path.join(root, name), explicit=False)
            if not recursive:
                break
        if not count and len(errors) == before_errors and not allow_empty:
            fail(path, "no_input_files")

    for item in inputs:
        if has_magic(item):
            matches = glob(item, recursive=recursive)
            if not matches and not allow_empty:
                fail(item, "glob_no_matches")
            for match in matches:
                visit(match)
        else:
            visit(item)
    if not out and not errors and not allow_empty:
        fail("(batch)", "no_input_files")
    return sorted(out), errors, skipped


# ─────────────────────────────────────────────────────────────────────
# 단일 파일 처리 (워커 진입점)
# ─────────────────────────────────────────────────────────────────────

def _process_single(
    args: tuple[
        str, str, str, str,
        Optional[tuple[str, ...]], Optional[tuple[str, ...]],
        tuple[str, ...],
        FileReadPolicy, float,
    ],
) -> FileResult:
    (
        input_path,
        output_path,
        mode,
        strategy,
        include,
        exclude,
        person_exclusions,
        read_policy,
        extraction_timeout,
    ) = args
    t0 = time.time()
    try:
        from ko_pii.anonymizer import Anonymizer
        from ko_pii.core.modes import Action, ProcessingMode as PM
        document = read_text_isolated(input_path, policy=read_policy, timeout=extraction_timeout)
        anon = Anonymizer(
            mode=PM(mode),
            strategy=strategy,
            include=include,
            exclude=exclude,
            person_exclusions=person_exclusions,
        )
        result = anon.process(document.text)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            write_text_atomic(output_path, result.text)

        n_block = sum(1 for r in result.detections if r.action == Action.BLOCK)
        n_review = sum(1 for r in result.detections if r.action == Action.REVIEW)
        return FileResult(
            input_path=input_path,
            output_path=output_path,
            detections=len(result.detections),
            combined_risk=result.combined_risk.combined_risk.name if result.combined_risk else "INFO",
            blocked=n_block,
            review=n_review,
            elapsed_s=time.time() - t0,
            coverage=document.coverage,
        )
    except Exception as e:
        return FileResult(
            input_path=input_path,
            output_path=None,
            detections=0,
            combined_risk="UNKNOWN",
            blocked=0,
            review=0,
            error=str(e) if isinstance(e, BoundedReadError) else f"{type(e).__name__}: processing failed",
            elapsed_s=time.time() - t0,
            error_code=e.code if isinstance(e, BoundedReadError) else "processing_failed",
            coverage=e.coverage if isinstance(e, BoundedReadError) else None,
        )


# ─────────────────────────────────────────────────────────────────────
# 공개 진입점
# ─────────────────────────────────────────────────────────────────────

def _output_path_for(
    input_path: str,
    output_dir: str,
    suffix: str = "",
) -> str:
    name = os.path.basename(input_path)
    stem, _ext = os.path.splitext(name)
    return os.path.join(output_dir, f"{stem}{suffix}.txt")


def process_paths(
    inputs: Iterable[str],
    output_dir: str,
    mode: ProcessingMode = ProcessingMode.STRICT,
    strategy: str = "tokenize",
    *,
    recursive: bool = True,
    workers: int = 1,
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    person_exclusions: Optional[Iterable[str]] = None,
    extensions: Optional[frozenset[str]] = None,
    progress: bool = True,
    read_policy: Optional[FileReadPolicy] = None,
    extraction_timeout: float = 30.0,
    allow_empty: bool = False,
    protected_paths: Iterable[str] = (),
) -> BatchSummary:
    """입력 파일·디렉토리·glob 들을 일괄 처리.

    Notes:
    -----
    워커 수와 관계없이 파일마다 별도 Anonymizer/Vault를 사용합니다. 문서 간 토큰
    일관성이나 감사 가능한 가역 Vault가 필요하면 단일 파일 API를 사용하십시오.
    protected_paths의 설정 파일과 예정 출력이 충돌하면 모든 쓰기 전에 거부합니다.
    """
    from ko_pii.patterns.person import normalize_exclusions

    normalized_exclusions = normalize_exclusions(person_exclusions)
    include_values = validate_label_filter(include, name="include")
    exclude_values = validate_label_filter(exclude, name="exclude")
    if workers < 1 or not math.isfinite(extraction_timeout) or extraction_timeout <= 0:
        raise ValueError("workers and extraction timeout must be positive")
    input_values = list(inputs)
    protected = [os.path.realpath(path) for path in protected_paths]
    output_root = os.path.realpath(output_dir)
    for value in input_values:
        if Path(os.path.realpath(value)).is_relative_to(output_root):
            raise ValueError("output directory must differ from and must not contain an input path")
    files, collection_errors, skipped = _collect_inputs(
        input_values, recursive, extensions, output_root=output_root, allow_empty=allow_empty,
    )
    summary = BatchSummary(total_files=len(files) + len(collection_errors), skipped=skipped)
    t0 = time.time()

    # 출력 경로 유일성 보장 — 서로 다른 디렉토리의 동명 파일이 같은
    # out/<stem>.txt 로 충돌해 마지막 결과가 이전 결과를 덮어쓰던 데이터 손실
    # 방지 (#12). 첫 파일은 <stem>.txt 유지, 충돌 시에만 입력경로 해시 부여.
    import hashlib

    seen_out: set[str] = set()
    args_list = []
    for f in files:
        out_path = _output_path_for(f, output_dir)
        if out_path.casefold() in seen_out:
            stem, ext = os.path.splitext(out_path)
            h = hashlib.sha1(os.path.abspath(f).encode("utf-8")).hexdigest()[:8]
            out_path = f"{stem}_{h}{ext}"
            number = 2
            while out_path.casefold() in seen_out:
                out_path = f"{stem}_{h}_{number}{ext}"
                number += 1
        seen_out.add(out_path.casefold())
        for path in protected:
            if (os.path.realpath(out_path) == path or
                    (os.path.exists(out_path) and os.path.exists(path)
                     and os.path.samefile(out_path, path))):
                raise ValueError("batch output conflicts with a protected configuration file")
        args_list.append((
            f,
            out_path,
            mode.value,
            strategy,
            include_values,
            exclude_values,
            tuple(sorted(normalized_exclusions)),
            read_policy or default_read_policy(),
            extraction_timeout,
        ))

    if workers <= 1:
        results = []
        for i, args in enumerate(args_list):
            r = _process_single(args)
            results.append(r)
            if progress:
                _print_progress(i + 1, len(files), r)
    else:
        with Pool(processes=workers) as pool:
            results = []
            for i, r in enumerate(pool.imap_unordered(_process_single, args_list)):
                results.append(r)
                if progress:
                    _print_progress(i + 1, len(files), r)

    for r in collection_errors + results:
        summary.results.append(r)
        if r.error:
            summary.failed += 1
        else:
            summary.succeeded += 1
            summary.total_detections += r.detections
            summary.total_blocked += r.blocked
            summary.total_review += r.review

    summary.elapsed_s = time.time() - t0
    if progress:
        sys.stderr.write("\n")
    return summary


def _print_progress(done: int, total: int, r: FileResult) -> None:
    pct = 100 * done / total if total else 100
    name = os.path.basename(r.input_path)[:40]
    status = "ERR" if r.error else f"{r.detections}d/{r.blocked}b/{r.review}r"
    sys.stderr.write(
        f"\r[{done}/{total}] {pct:5.1f}%  {name:40s}  {status:20s}"
    )
    sys.stderr.flush()
