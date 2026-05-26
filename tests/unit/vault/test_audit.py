from ko_pii.core.types import RiskLevel
from ko_pii.vault.audit import AuditLog, replay
from ko_pii.vault.reversible import ReversibleVault


class TestAuditLog:
    def test_basic_recording(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with AuditLog(log_path) as log:
            log.record_store("<RRN_1>", "RRN", actor="alice")
            log.record_reveal("<RRN_1>", "RRN", actor="bob",
                              context="export to BI")

        entries = replay(log_path)
        assert len(entries) == 2
        assert entries[0]["action"] == "store"
        assert entries[0]["actor"] == "alice"
        assert entries[1]["action"] == "reveal"
        assert entries[1]["context"] == "export to BI"

    def test_vault_integration(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with AuditLog(log_path) as log:
            v = ReversibleVault(salt="x", audit_log=log)
            v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))
            v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))  # 중복 — 1번만 store 기록
            original = v.reveal("<RRN_1>", context="legitimate request")
            assert original == "880101-1234568"

        entries = replay(log_path)
        # store 1번 + reveal 1번
        assert sum(1 for e in entries if e["action"] == "store") == 1
        assert sum(1 for e in entries if e["action"] == "reveal") == 1
        # reveal 항목에 context 보존
        reveal_entry = next(e for e in entries if e["action"] == "reveal")
        assert reveal_entry["context"] == "legitimate request"

    def test_replay_missing_file(self, tmp_path):
        assert replay(str(tmp_path / "no_such.jsonl")) == []

    def test_attach_audit_after_init(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        v = ReversibleVault(salt="x")
        v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))  # 감사 X
        with AuditLog(log_path) as log:
            v.attach_audit(log)
            v.reveal("<RRN_1>", context="now logged")
        entries = replay(log_path)
        assert len(entries) == 1
        assert entries[0]["action"] == "reveal"
