"""Single-file replacement without truncating an existing destination."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


def write_bytes_atomic(path: str | Path, content: bytes) -> None:
    """Stage privately on the same filesystem, flush, then replace the file.

    This is one file's commit boundary, not a multi-file transaction or a lock
    against concurrent writers. New files have owner-only permissions.
    """
    target = Path(path)
    if target.is_symlink():
        raise ValueError("output must not be a symbolic link")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_text_atomic(path: str | Path, content: str) -> None:
    write_bytes_atomic(path, content.encode("utf-8"))
