"""Vault 감사 로그 — 모든 ``reveal()`` / ``store()`` 호출 추적.

처리 이력을 남기기 위한 로컬 기록 도구다. 이것만으로 접근통제·무결성 보호 또는
법적 준수를 보장하지 않는다.

저장 포맷: JSON Lines (``.jsonl``) — append 방식이며 검색·집계에 적합하다.
각 라인:
  {"ts": "ISO-8601", "action": "reveal", "token": "<RRN_1>", "label": "RRN",
   "actor": "user@host", "context": "..."}

특징:
- 단일 프로세스 안에서 thread-safe
- 각 레코드마다 flush하지만 프로세스 간 원자성·fsync·변조 방지는 제공하지 않음
- ``with AuditLog(path) as log:`` 컨텍스트 매니저
- 라인 부분 손상 무시 (마지막 줄만 잘릴 수 있음)
"""
from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone
from types import TracebackType
from typing import Any, Optional, TextIO


class AuditLog:
    """Append-style JSONL 감사 로그.

    The file remains mutable by any principal with filesystem write access.
    Use external access control and integrity protection when it is an audit
    trust boundary.

    Usage::

        with AuditLog("vault_audit.jsonl") as log:
            log.record_reveal("<RRN_1>", "RRN", actor="alice")
    """

    _LOCK = threading.Lock()

    def __init__(self, path: str, default_actor: Optional[str] = None) -> None:
        self.path = path
        self.default_actor = default_actor or self._detect_actor()
        self._fh: Optional[TextIO] = None

    @staticmethod
    def _detect_actor() -> str:
        user = "unknown"
        try:
            user = os.getlogin()
        except (OSError, AttributeError):
            user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        try:
            host = socket.gethostname()
        except Exception:
            host = "host"
        return f"{user}@{host}"

    def __enter__(self) -> "AuditLog":
        self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _open_if_needed(self) -> TextIO:
        if self._fh is None:
            self._fh = open(self.path, "a", encoding="utf-8", buffering=1)
        return self._fh

    # ------------------------------------------------------------ public

    def record(
        self,
        action: str,
        *,
        token: Optional[str] = None,
        label: Optional[str] = None,
        actor: Optional[str] = None,
        context: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "token": token,
            "label": label,
            "actor": actor or self.default_actor,
            "context": context,
        }
        if extra:
            entry["extra"] = extra
        line = json.dumps(entry, ensure_ascii=False)
        with self._LOCK:
            fh = self._open_if_needed()
            fh.write(line + "\n")
            fh.flush()

    # 의미 있는 헬퍼들
    def record_store(self, token: str, label: str, **kw: Any) -> None:
        self.record("store", token=token, label=label, **kw)

    def record_reveal(
        self, token: str, label: Optional[str] = None, **kw: Any
    ) -> None:
        self.record("reveal", token=token, label=label, **kw)

    def record_anonymize(
        self,
        count: int,
        mode: str,
        *,
        status: str = "completed",
        **kw: Any,
    ) -> None:
        self.record(
            "anonymize",
            extra={"count": count, "mode": mode, "status": status},
            **kw,
        )


def replay(path: str) -> list[dict[str, Any]]:
    """JSONL 로그를 dict 리스트로 로드 (분석·감사용)."""
    out: list[dict[str, Any]] = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
