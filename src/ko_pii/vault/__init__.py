"""Reversible pseudonymization vault — stores original PII for authorized recovery.

Optional submodules:
- ``encrypted`` (requires ``cryptography``) — AES-GCM Vault 암호화
- ``audit`` (stdlib) — 모든 store/reveal 호출 추적
"""
from ko_pii.vault.audit import AuditLog, replay
from ko_pii.vault.reversible import ReversibleVault, VaultEntry

__all__ = ["ReversibleVault", "VaultEntry", "AuditLog", "replay"]
