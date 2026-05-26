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
