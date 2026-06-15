"""가역 가명화 Vault (Reversible pseudonymization vault).

핵심 아이디어:
- 검출된 원본 PII는 외부에 직접 노출되지 않고 Vault 에만 저장된다.
- 본문에는 카테고리별 토큰 (예: ``<RRN_1>``) 으로 치환된다.
- Vault 를 보유한 권한 있는 사용자만 토큰으로부터 원본을 복원할 수 있다.

Vault JSON schema v1::

    {
        "schema_version": 1,
        "created_at": "ISO-8601",
        "salt": "<hex-string>",          // 토큰 해시에 사용 (식별자 일관성)
        "entries": {
            "<RRN_1>": {
                "label": "RRN",
                "original": "880101-1234568",
                "risk_level": 5,
                "legal_basis": "개인정보보호법 제24조의2",
                "first_seen_offset": 12,
                "occurrences": [12, 200]
            },
            ...
        }
    }

같은 원본 값은 같은 토큰을 받는다 (문서 내 일관성). 이는 hashlib 기반 안정 키로
보장된다.

Legal basis: 개인정보보호법 제28조의2~5 (가명정보 처리 특례) — 가명처리된 정보가
"추가 정보 (즉, 본 Vault) 없이는 특정 개인을 알아볼 수 없도록" 분리 보관되어야 함.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .audit import AuditLog

SCHEMA_VERSION = 1

# 지문(fingerprint) KDF 반복 횟수 기본값 — 저엔트로피 PII 무차별 대입을 늦춘다.
# (실제 보안의 핵심은 secret_key: 키가 있으면 키 없이는 대입 자체가 불가능.)
_DEFAULT_FP_ITERATIONS = 100_000
_FP_SCHEME_LEGACY = "sha256-v1"        # 강화 전 vault (불려온 경우 호환 유지)
_FP_SCHEME_KDF = "pbkdf2-sha256-v2"    # 신규 vault 기본


@dataclass
class VaultEntry:
    token: str
    label: str
    original: str
    risk_level: int
    legal_basis: Optional[str] = None
    first_seen_offset: int = -1
    occurrences: list[int] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("token")
        return d


class ReversibleVault:
    """In-memory vault that maps tokens to original PII values.

    Tokens are deterministic per (label, original) pair so that the same value
    receives the same token throughout a document — and across multiple runs
    if the same ``salt`` is reused.
    """

    def __init__(
        self,
        salt: Optional[str] = None,
        audit_log: Optional["AuditLog"] = None,
        secret_key: Optional[str] = None,
        fingerprint_iterations: Optional[int] = None,
    ) -> None:
        """``audit_log``: optional :class:`AuditLog` for compliance tracking.

        When provided, every ``store()`` and ``reveal()`` call is appended to
        the log — directly answering 개인정보보호법 제29조 안전조치의무 의
        처리 이력 요건.

        ``secret_key``: hashed/FPE 지문용 비밀 키(pepper). 미지정 시 env
        ``KPII_FINGERPRINT_KEY`` 사용. **vault JSON 에 저장되지 않는다.** salt 는
        공개돼도 무방하지만, salt 만으론 저엔트로피 PII(주민·전화 등)가 무차별
        대입으로 복원될 수 있어 비밀 키가 권장된다. 실행 간 hashed/FPE 출력
        일관성을 위해선 같은 키(+같은 vault)를 재사용해야 한다.
        """
        self.salt: str = salt if salt is not None else _random_salt()
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self._entries: dict[str, VaultEntry] = {}
        self._reverse: dict[tuple[str, str], str] = {}  # (label, original) -> token
        self._counters: dict[str, int] = {}             # label -> next id
        self._audit: Optional["AuditLog"] = audit_log
        self._secret_key: str = (
            secret_key if secret_key is not None
            else os.environ.get("KPII_FINGERPRINT_KEY", "")
        )
        self._fp_iterations: int = fingerprint_iterations or _DEFAULT_FP_ITERATIONS
        self._fp_scheme: str = _FP_SCHEME_KDF          # 신규 vault = 강화 KDF
        self._fp_cache: dict[tuple[str, str], str] = {}  # (label,original)->fp 메모이즈

    # ------------------------------------------------------------------ token

    def token_for(self, label: str, original: str) -> str:
        """Return a stable token for (label, original). Creates one on first use."""
        key = (label, original)
        existing = self._reverse.get(key)
        if existing is not None:
            return existing
        self._counters[label] = self._counters.get(label, 0) + 1
        token = f"<{label}_{self._counters[label]}>"
        self._reverse[key] = token
        return token

    def store(
        self,
        label: str,
        original: str,
        risk_level: int,
        legal_basis: Optional[str] = None,
        offset: int = -1,
        extra: Optional[dict[str, Any]] = None,
    ) -> str:
        """Insert or update an entry; return the assigned token."""
        token = self.token_for(label, original)
        entry = self._entries.get(token)
        is_new = entry is None
        if entry is None:
            entry = VaultEntry(
                token=token,
                label=label,
                original=original,
                risk_level=risk_level,
                legal_basis=legal_basis,
                first_seen_offset=offset,
                occurrences=[offset] if offset >= 0 else [],
                extra=dict(extra or {}),
            )
            self._entries[token] = entry
        else:
            if offset >= 0:
                entry.occurrences.append(offset)
        if self._audit is not None:
            try:
                # 모든 store 호출 기록 (재저장 포함). new=False 면 기존 토큰 재사용.
                self._audit.record_store(token, label, extra={"new": is_new})
            except Exception:
                pass  # audit failure never blocks data flow
        return token

    # ---------------------------------------------------------------- lookup

    def reveal(self, token: str, *, context: Optional[str] = None) -> Optional[str]:
        """Return the original value for a token, or None if unknown.

        ``context`` (optional) is recorded in the audit log — use it to attach
        a reason ("export to BI dashboard", "user request id=42", etc.).
        """
        entry = self._entries.get(token)
        if self._audit is not None:
            try:
                # 실패(존재하지 않는 토큰 probing)도 기록 — found=False 로 표시.
                self._audit.record_reveal(
                    token,
                    entry.label if entry is not None else None,
                    context=context,
                    extra={"found": entry is not None},
                )
            except Exception:
                pass
        return entry.original if entry is not None else None

    def attach_audit(self, audit_log: "AuditLog") -> None:
        """Attach (or replace) an :class:`AuditLog` after construction."""
        self._audit = audit_log

    def get(self, token: str) -> Optional[VaultEntry]:
        return self._entries.get(token)

    def __contains__(self, token: str) -> bool:
        return token in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> list[VaultEntry]:
        return list(self._entries.values())

    def labels(self) -> set[str]:
        return {e.label for e in self._entries.values()}

    # ------------------------------------------------------- persistence

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "created_at": self.created_at,
            "salt": self.salt,
            "fingerprint_scheme": self._fp_scheme,        # secret_key 는 저장 X
            "fingerprint_iterations": self._fp_iterations,
            "entries": {
                token: entry.to_dict() for token, entry in self._entries.items()
            },
        }

    def dumps(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def save(self, path: str, indent: Optional[int] = 2) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.dumps(indent=indent))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReversibleVault":
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported vault schema_version: {payload.get('schema_version')}"
            )
        v = cls(salt=payload["salt"])
        v.created_at = payload.get("created_at", v.created_at)
        # 강화 전(legacy) vault 는 fingerprint_scheme 필드가 없음 → SHA-256 v1 유지
        # (불려온 vault 의 hashed/FPE 출력 일관성 보존). secret_key 는 env 에서.
        v._fp_scheme = payload.get("fingerprint_scheme", _FP_SCHEME_LEGACY)
        v._fp_iterations = int(payload.get("fingerprint_iterations", v._fp_iterations))
        for token, data in payload.get("entries", {}).items():
            entry = VaultEntry(
                token=token,
                label=data["label"],
                original=data["original"],
                risk_level=data["risk_level"],
                legal_basis=data.get("legal_basis"),
                first_seen_offset=data.get("first_seen_offset", -1),
                occurrences=list(data.get("occurrences", [])),
                extra=dict(data.get("extra", {})),
            )
            v._entries[token] = entry
            v._reverse[(entry.label, entry.original)] = token
            # Maintain counters so future stores don't collide.
            try:
                n = int(token.rsplit("_", 1)[-1].rstrip(">"))
            except ValueError:
                continue
            cur = v._counters.get(entry.label, 0)
            if n > cur:
                v._counters[entry.label] = n
        return v

    @classmethod
    def loads(cls, payload: str) -> "ReversibleVault":
        return cls.from_dict(json.loads(payload))

    @classmethod
    def load(cls, path: str) -> "ReversibleVault":
        with open(path, "r", encoding="utf-8") as f:
            return cls.loads(f.read())

    # ----------------------------------------------------- hash-based id

    def fingerprint(self, label: str, original: str) -> str:
        """``(label, original)`` 의 안정적·비가역 지문 (hashed/FPE 모드용).

        강화 scheme(``pbkdf2-sha256-v2``): 비밀 키(pepper)를 섞은 salt 위에
        PBKDF2-HMAC-SHA256 을 ``iterations`` 회 적용 — 저엔트로피 PII 의 무차별
        대입을 막는다. 비밀 키가 있으면 키 없이는 대입 자체가 불가능하고, 키가
        없어도 stretching 으로 비용을 높인다. (legacy vault 는 기존 SHA-256 유지.)
        같은 값은 메모이즈되어 KDF 비용이 *고유 값당 1회* 로 제한된다.
        """
        cache_key = (label, original)
        cached = self._fp_cache.get(cache_key)
        if cached is not None:
            return cached
        if self._fp_scheme == _FP_SCHEME_LEGACY:
            h = hashlib.sha256()
            h.update(self.salt.encode("utf-8"))
            h.update(b":")
            h.update(label.encode("utf-8"))
            h.update(b":")
            h.update(original.encode("utf-8"))
            fp = h.hexdigest()
        else:
            material = f"{label}:{original}".encode("utf-8")
            # 비밀 키를 salt 에 결합 — 키가 vault JSON 에 없으므로, 키 없이는
            # salt 를 알아도 (label,original) 을 복원할 수 없다.
            kdf_salt = f"{self.salt}:{self._secret_key}".encode("utf-8")
            fp = hashlib.pbkdf2_hmac(
                "sha256", material, kdf_salt, self._fp_iterations
            ).hex()
        self._fp_cache[cache_key] = fp
        return fp


def _random_salt(n_bytes: int = 16) -> str:
    return os.urandom(n_bytes).hex()
