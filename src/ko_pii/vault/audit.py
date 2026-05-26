"""Vault 감사 로그 — 모든 ``reveal()`` / ``store()`` 호출 추적.

개인정보보호법 제29조 (안전조치의무) 의 *처리 이력 기록* 요건 직접 대응.

저장 포맷: JSON Lines (``.jsonl``) — append-only, 검색·집계 친화적.
각 라인:
  {"ts": "ISO-8601", "action": "reveal", "token": "<RRN_1>", "label": "RRN",
   "actor": "user@host", "context": "..."}

특징:
- thread-safe (다중 워커에서도 안전 append)
- 원자적 write (한 라인 통째 flush)
- ``with AuditLog(path) as log:`` 컨텍스트 매니저
- 라인 부분 손상 무시 (마지막 줄만 잘릴 수 있음)
"""
from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timezone
from typing import Optional


class AuditLog:
    """Append-only JSONL 감사 로그.

    Usage::

        with AuditLog("vault_audit.jsonl") as log:
            log.record_reveal("<RRN_1>", "RRN", actor="alice")
    """

    _LOCK = threading.Lock()

    def __init__(self, path: str, default_actor: Optional[str] = None):
        self.path = path
        self.default_actor = default_actor or self._detect_actor()
        self._fh = None

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

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _open_if_needed(self):
        if self._fh is None:
            self._fh = open(self.path, "a", encoding="utf-8", buffering=1)

    # ------------------------------------------------------------ public

    def record(
        self,
        action: str,
        *,
        token: Optional[str] = None,
        label: Optional[str] = None,
        actor: Optional[str] = None,
        context: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> None:
        entry = {
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
            self._open_if_needed()
            self._fh.write(line + "\n")
            try:
                self._fh.flush()
            except Exception:
                pass

    # 의미 있는 헬퍼들
    def record_store(self, token: str, label: str, **kw) -> None:
        self.record("store", token=token, label=label, **kw)

    def record_reveal(self, token: str, label: Optional[str] = None, **kw) -> None:
        self.record("reveal", token=token, label=label, **kw)

    def record_anonymize(self, count: int, mode: str, **kw) -> None:
        self.record("anonymize", extra={"count": count, "mode": mode}, **kw)


def replay(path: str) -> list[dict]:
    """JSONL 로그를 dict 리스트로 로드 (분석·감사용)."""
    out: list[dict] = []
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
