"""Run bounded extraction outside the caller with a wall-clock timeout."""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import sys

from ko_pii.io_.bounded import BoundedDocument, BoundedReadError, FileReadPolicy
from ko_pii.io_.dispatcher import SUPPORTED_EXTENSIONS


def default_read_policy() -> FileReadPolicy:
    # Legacy PDF/HWP parsers run in the worker, not in the calling process.
    return FileReadPolicy(allowed_extensions=SUPPORTED_EXTENSIONS)


def read_text_isolated(
    path: str | Path,
    *,
    policy: FileReadPolicy | None = None,
    timeout: float = 30.0,
) -> BoundedDocument:
    """Apply file/archive/text limits and terminate extraction on timeout.

    The worker also caps address space at 512 MiB on Linux. Other platforms
    retain the timeout and file limits, but do not enforce a memory ceiling.
    This is resource isolation, not an OS security sandbox.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("extraction timeout must be finite and positive")
    active = policy or default_read_policy()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "ko_pii.io_._worker", str(Path(path).absolute())],
            input=json.dumps(asdict(active)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise BoundedReadError("extract_timeout", "document extraction exceeded the time limit") from None
    except OSError:
        raise BoundedReadError("extractor_unavailable", "document extraction worker could not start") from None
    try:
        payload = json.loads(completed.stdout)
    except (ValueError, TypeError):
        raise BoundedReadError("extract_worker_failed", "document extraction worker failed") from None
    if completed.returncode != 0:
        if isinstance(payload, dict) and isinstance(payload.get("code"), str):
            raise BoundedReadError(payload["code"], payload.get("message", "extraction failed"))
        raise BoundedReadError("extract_worker_failed", "document extraction worker failed")
    try:
        return BoundedDocument(**payload)
    except (TypeError, ValueError):
        raise BoundedReadError("extract_worker_failed", "invalid extraction worker result") from None
