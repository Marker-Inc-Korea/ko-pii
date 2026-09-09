"""Reversible pseudonymization storage primitives.

The vault does not authenticate callers. Applications must enforce access control.

Optional submodules:
- ``encrypted`` (requires ``cryptography``) — AES-GCM Vault 암호화
- ``audit`` (stdlib) — 모든 store/reveal 호출 추적
"""
from ko_pii.vault.audit import AuditLog, replay
from ko_pii.vault.reversible import AuditFailurePolicy, ReversibleVault, VaultEntry

__all__ = [
    "ReversibleVault",
    "VaultEntry",
    "AuditFailurePolicy",
    "AuditLog",
    "replay",
]
