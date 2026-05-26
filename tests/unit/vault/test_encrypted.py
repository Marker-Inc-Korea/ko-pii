import pytest

from ko_pii.core.types import RiskLevel
from ko_pii.vault.reversible import ReversibleVault

try:
    import cryptography  # noqa: F401 — runtime dep for ko_pii.vault.encrypted
    from ko_pii.vault.encrypted import save_encrypted, load_encrypted, is_encrypted_file
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


pytestmark = pytest.mark.skipif(
    not HAS_CRYPTO, reason="cryptography 미설치 — ko-pii[security] 필요"
)


class TestEncryption:
    def test_round_trip(self, tmp_path):
        v = ReversibleVault(salt="abc")
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        v.store("PHONE", "010-1234-5678", int(RiskLevel.MEDIUM))
        path = str(tmp_path / "vault.kvault")
        save_encrypted(v, path, password="mysecret123")

        # 파일이 암호화되었는지 확인
        assert is_encrypted_file(path)

        # 복호화
        v2 = load_encrypted(path, password="mysecret123")
        assert v2.reveal("<RRN_1>") == "880101-1234568"
        assert v2.reveal("<PHONE_1>") == "010-1234-5678"
        assert v2.salt == "abc"

    def test_wrong_password_fails(self, tmp_path):
        v = ReversibleVault()
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        path = str(tmp_path / "vault.kvault")
        save_encrypted(v, path, "right_password")
        with pytest.raises(ValueError):
            load_encrypted(path, "wrong_password")

    def test_empty_password_rejected(self, tmp_path):
        v = ReversibleVault()
        path = str(tmp_path / "vault.kvault")
        with pytest.raises(ValueError):
            save_encrypted(v, path, "")

    def test_not_encrypted_file(self, tmp_path):
        path = tmp_path / "plain.json"
        path.write_text('{"schema_version": 1, "salt": "x", "entries": {}}')
        assert not is_encrypted_file(str(path))

    def test_magic_byte_check(self, tmp_path):
        path = tmp_path / "garbage.dat"
        path.write_bytes(b"not a vault")
        assert not is_encrypted_file(str(path))
        with pytest.raises(ValueError):
            load_encrypted(str(path), "any")
