"""배치 / 병렬 처리 — 디렉토리·glob 패턴 일괄 가명화.

특징:
- ``multiprocessing.Pool`` 로 워커 병렬화 (stdlib)
- 진행률 표시 (stderr 라인 갱신, 외부 deps 없이)
- 입력 파일별 결과를 *대응되는 출력 경로* 에 기록
- Vault 는 *옵션* — 공유하면 문서 간 토큰 일관성 (같은 사람 → 같은 토큰)
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
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Iterable, Optional

from ko_pii.core.modes import ProcessingMode


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
    exts = extensions or DEFAULT_EXTENSIONS
    seen: set[str] = set()
    out: list[str] = []

    def _add_if_ok(p: str) -> None:
        if p in seen:
            return
        if not os.path.isfile(p):
            return
        if os.path.splitext(p)[1].lower() not in exts:
            return
        seen.add(p)
        out.append(p)

    for item in inputs:
        # Glob support
        if any(ch in item for ch in "*?["):
            from glob import glob
            for p in glob(item, recursive=recursive):
                _add_if_ok(p)
            continue
        if os.path.isfile(item):
            _add_if_ok(item)
            continue
        if os.path.isdir(item):
            if recursive:
                for root, _dirs, files in os.walk(item):
                    for fname in files:
                        _add_if_ok(os.path.join(root, fname))
            else:
                for fname in os.listdir(item):
                    _add_if_ok(os.path.join(item, fname))
    return sorted(out)


# ─────────────────────────────────────────────────────────────────────
# 단일 파일 처리 (워커 진입점)
# ─────────────────────────────────────────────────────────────────────

def _process_single(args: tuple) -> FileResult:
    (input_path, output_path, mode, strategy, include, exclude) = args
    t0 = time.time()
    try:
        from ko_pii.anonymizer import Anonymizer
        from ko_pii.core.modes import Action, ProcessingMode as PM
        from ko_pii.io_ import read_text

        text = read_text(input_path)
        anon = Anonymizer(
            mode=PM(mode),
            strategy=strategy,
            include=list(include) if include else None,
            exclude=list(exclude) if exclude else None,
        )
        result = anon.process(text)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result.text)

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
        )
    except Exception as e:
        return FileResult(
            input_path=input_path,
            output_path=None,
            detections=0,
            combined_risk="UNKNOWN",
            blocked=0,
            review=0,
            error=f"{type(e).__name__}: {e}",
            elapsed_s=time.time() - t0,
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
    extensions: Optional[frozenset[str]] = None,
    progress: bool = True,
) -> BatchSummary:
    """입력 파일·디렉토리·glob 들을 일괄 처리.

    Notes:
    -----
    워커가 1 이면 in-process 처리 (vault 공유 가능). 2 이상이면 multiprocessing
    이므로 *vault 공유 불가* — 각 워커는 자체 vault. 토큰 일관성이 필요하면
    workers=1 사용.
    """
    files = collect_files(inputs, recursive=recursive, extensions=extensions)
    summary = BatchSummary(total_files=len(files))
    t0 = time.time()

    args_list = [
        (
            f,
            _output_path_for(f, output_dir),
            mode.value,
            strategy,
            tuple(include) if include else None,
            tuple(exclude) if exclude else None,
        )
        for f in files
    ]

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

    for r in results:
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
