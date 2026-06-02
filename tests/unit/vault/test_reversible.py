import json

import pytest

from ko_pii.core.types import RiskLevel
from ko_pii.vault.reversible import ReversibleVault


class TestTokenAssignment:
    def test_same_value_gets_same_token(self):
        v = ReversibleVault(salt="abc")
        t1 = v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        t2 = v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        assert t1 == t2 == "<RRN_1>"

    def test_different_values_get_different_tokens(self):
        v = ReversibleVault(salt="abc")
        a = v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        b = v.store("RRN", "950101-2345676", int(RiskLevel.CRITICAL))
        assert a == "<RRN_1>"
        assert b == "<RRN_2>"

    def test_per_label_counters(self):
        v = ReversibleVault(salt="abc")
        a = v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        b = v.store("PHONE", "010-1234-5678", int(RiskLevel.MEDIUM))
        assert a == "<RRN_1>"
        assert b == "<PHONE_1>"

    def test_reveal_round_trip(self):
        v = ReversibleVault(salt="abc")
        token = v.store(
            "EMAIL", "user@example.com", int(RiskLevel.MEDIUM),
            legal_basis="개인정보보호법 제2조",
        )
        assert v.reveal(token) == "user@example.com"
        assert v.reveal("<NONEXISTENT_99>") is None

    def test_occurrences_accumulate(self):
        v = ReversibleVault(salt="abc")
        v.store("EMAIL", "a@b.c", int(RiskLevel.MEDIUM), offset=10)
        v.store("EMAIL", "a@b.c", int(RiskLevel.MEDIUM), offset=50)
        v.store("EMAIL", "a@b.c", int(RiskLevel.MEDIUM), offset=120)
        entry = v.get("<EMAIL_1>")
        assert entry is not None
        assert entry.occurrences == [10, 50, 120]
        assert entry.first_seen_offset == 10


class TestPersistence:
    def test_dumps_is_valid_json_v1(self):
        v = ReversibleVault(salt="abc")
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL),
                legal_basis="개인정보보호법 제24조의2", offset=5)
        payload = json.loads(v.dumps())
        assert payload["schema_version"] == 1
        assert payload["salt"] == "abc"
        assert "<RRN_1>" in payload["entries"]
        e = payload["entries"]["<RRN_1>"]
        assert e["original"] == "880101-1234568"
        assert e["risk_level"] == int(RiskLevel.CRITICAL)
        assert e["legal_basis"] == "개인정보보호법 제24조의2"

    def test_load_round_trip(self):
        v = ReversibleVault(salt="abc")
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL), offset=5)
        v.store("PHONE", "010-1234-5678", int(RiskLevel.MEDIUM), offset=20)
        payload = v.dumps()
        v2 = ReversibleVault.loads(payload)
        assert v2.salt == "abc"
        assert v2.reveal("<RRN_1>") == "880101-1234568"
        assert v2.reveal("<PHONE_1>") == "010-1234-5678"

    def test_load_preserves_counters(self):
        v = ReversibleVault(salt="abc")
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
        v.store("RRN", "950101-2345676", int(RiskLevel.CRITICAL))
        payload = v.dumps()
        v2 = ReversibleVault.loads(payload)
        # New store should get RRN_3, not collide with existing RRN_1/2
        t = v2.store("RRN", "100101-3000005", int(RiskLevel.CRITICAL))
        assert t == "<RRN_3>"

    def test_save_and_load_file(self, tmp_path):
        v = ReversibleVault(salt="abc")
        v.store("EMAIL", "a@b.c", int(RiskLevel.MEDIUM))
        p = tmp_path / "vault.json"
        v.save(str(p))
        v2 = ReversibleVault.load(str(p))
        assert v2.reveal("<EMAIL_1>") == "a@b.c"

    def test_rejects_unknown_schema_version(self):
        with pytest.raises(ValueError):
            ReversibleVault.from_dict({"schema_version": 99, "salt": "x", "entries": {}})


class TestFingerprint:
    def test_fingerprint_is_stable(self):
        v = ReversibleVault(salt="known-salt")
        f1 = v.fingerprint("RRN", "880101-1234568")
        f2 = v.fingerprint("RRN", "880101-1234568")
        assert f1 == f2
        assert len(f1) == 64  # sha256 hex

    def test_fingerprint_changes_with_salt(self):
        a = ReversibleVault(salt="salt-a").fingerprint("RRN", "880101-1234568")
        b = ReversibleVault(salt="salt-b").fingerprint("RRN", "880101-1234568")
        assert a != b

    def test_fingerprint_changes_with_label(self):
        v = ReversibleVault(salt="x")
        a = v.fingerprint("RRN", "880101-1234568")
        b = v.fingerprint("CORP_REG", "880101-1234568")
        assert a != b


class TestFingerprintHardening:
    """지문 KDF 강화 (비밀 키 + PBKDF2) — 저엔트로피 PII 무차별 대입 방어."""

    def test_fingerprint_is_secret_key_dependent(self):
        a = ReversibleVault(salt="s", secret_key="k1", fingerprint_iterations=1000)
        b = ReversibleVault(salt="s", secret_key="k2", fingerprint_iterations=1000)
        assert a.fingerprint("RRN", "900101-1234567") != b.fingerprint("RRN", "900101-1234567")

    def test_secret_key_not_persisted(self):
        v = ReversibleVault(salt="s", secret_key="topsecret", fingerprint_iterations=1000)
        d = v.to_dict()
        assert "secret_key" not in d
        assert "topsecret" not in json.dumps(d)

    def test_saltonly_attacker_cannot_reproduce(self):
        # vault JSON(salt·scheme·iters)만 가진 공격자는 비밀 키 없이 지문 재현 불가
        v = ReversibleVault(salt="s", secret_key="k", fingerprint_iterations=1000)
        target = v.fingerprint("RRN", "900101-1234567")
        pub = v.to_dict()
        attacker = ReversibleVault(
            salt=pub["salt"], fingerprint_iterations=pub["fingerprint_iterations"]
        )
        attacker._fp_scheme = pub["fingerprint_scheme"]
        assert attacker.fingerprint("RRN", "900101-1234567") != target

    def test_legacy_vault_keeps_sha256_scheme(self):
        import hashlib
        legacy = {"schema_version": 1, "created_at": "t", "salt": "s", "entries": {}}
        v = ReversibleVault.from_dict(legacy)
        expected = hashlib.sha256(b"s:RRN:900101-1234567").hexdigest()
        assert v.fingerprint("RRN", "900101-1234567") == expected

    def test_kdf_fingerprint_deterministic_after_reload(self):
        v = ReversibleVault(salt="s", secret_key="k", fingerprint_iterations=1000)
        before = v.fingerprint("RRN", "900101-1234567")
        v2 = ReversibleVault.from_dict(v.to_dict())
        v2._secret_key = "k"  # 운영자가 같은 키를 env/param 으로 재공급
        assert v2.fingerprint("RRN", "900101-1234567") == before

    def test_env_secret_key_used(self, monkeypatch):
        monkeypatch.setenv("KPII_FINGERPRINT_KEY", "envkey")
        with_env = ReversibleVault(salt="s", fingerprint_iterations=1000)
        monkeypatch.delenv("KPII_FINGERPRINT_KEY")
        without = ReversibleVault(salt="s", fingerprint_iterations=1000)
        assert with_env.fingerprint("RRN", "900101-1234567") != without.fingerprint("RRN", "900101-1234567")
