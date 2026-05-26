"""Vault 암호화 — 개인정보보호법 제29조 (안전조치의무) 직접 대응.

알고리즘:
- AES-256-GCM (NIST SP 800-38D, 안전·검증된 AEAD)
- 키 유도: PBKDF2-HMAC-SHA256 (RFC 8018), 480,000 iterations (OWASP 2023 권장)
- Salt: 16 bytes (per-vault), Nonce: 12 bytes (per-encryption)
- 평문 JSON 을 *통째로* 암호화 → 단일 파일로 저장

외부 의존성: ``cryptography`` (Apache-2.0, 잘 검증됨).
``pip install ko-pii[security]`` 로 설치.

파일 포맷 (.kvault):
  magic(8) + version(1) + kdf_salt(16) + nonce(12) + ciphertext(...) + tag(16)
  magic = b"KPIIVT\\x01\\x00"

복호화 실패 (잘못된 비밀번호) 시 ``ValueError`` 발생.
"""
from __future__ import annotations

import hashlib
import os
import struct

from ko_pii.vault.reversible import ReversibleVault

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


MAGIC = b"KPIIVT\x01\x00"   # 8 bytes (대문자 KPIIVT + version 1.0)
KDF_ITERATIONS = 480_000
KDF_SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32                  # AES-256


def _ensure_crypto() -> None:
    if not _HAS_CRYPTO:
        raise ImportError(
            "Vault 암호화는 'cryptography' 패키지가 필요합니다.\n"
            "  pip install ko-pii[security]\n"
            "또는 pip install cryptography"
        )


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        KDF_ITERATIONS,
        dklen=KEY_LEN,
    )


def save_encrypted(vault: ReversibleVault, path: str, password: str) -> None:
    """Encrypt the vault and write to *path*.

    ``password`` is the user-supplied passphrase. Keep it out of source code —
    use environment variables or a key management service in production.
    """
    _ensure_crypto()
    if not password:
        raise ValueError("password must be non-empty")
    salt = os.urandom(KDF_SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(password, salt)
    aead = AESGCM(key)
    plaintext = vault.dumps(indent=None).encode("utf-8")
    # AAD = magic + version → integrity binds to the file format
    aad = MAGIC
    ciphertext = aead.encrypt(nonce, plaintext, aad)
    with open(path, "wb") as f:
        f.write(MAGIC)
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)


def load_encrypted(path: str, password: str) -> ReversibleVault:
    """Decrypt and return a vault. Raises ValueError on wrong password."""
    _ensure_crypto()
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < len(MAGIC) + KDF_SALT_LEN + NONCE_LEN + 16:
        raise ValueError("vault file truncated or invalid")
    if data[:len(MAGIC)] != MAGIC:
        raise ValueError("not a ko-pii encrypted vault (magic mismatch)")
    pos = len(MAGIC)
    salt = data[pos:pos + KDF_SALT_LEN]; pos += KDF_SALT_LEN
    nonce = data[pos:pos + NONCE_LEN]; pos += NONCE_LEN
    ciphertext = data[pos:]
    key = _derive_key(password, salt)
    aead = AESGCM(key)
    try:
        plaintext = aead.decrypt(nonce, ciphertext, MAGIC)
    except Exception as e:
        raise ValueError(f"decryption failed (wrong password or corruption): {e}") from e
    return ReversibleVault.loads(plaintext.decode("utf-8"))


def is_encrypted_file(path: str) -> bool:
    """파일이 암호화된 vault 인지 확인 (magic byte 검사)."""
    try:
        with open(path, "rb") as f:
            head = f.read(len(MAGIC))
        return head == MAGIC
    except OSError:
        return False
