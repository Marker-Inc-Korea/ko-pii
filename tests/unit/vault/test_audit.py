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
            v.store("RRN", "880101-1234568", int(RiskLevel.CRITICAL))  # 재저장도 기록(new=False)
            original = v.reveal("<RRN_1>", context="legitimate request")
            assert original == "880101-1234568"
            v.reveal("<NOPE_9>")  # 실패(probing) reveal — 보안상 반드시 기록

        entries = replay(log_path)
        stores = [e for e in entries if e["action"] == "store"]
        reveals = [e for e in entries if e["action"] == "reveal"]
        # 모든 store 호출 기록 (재저장 포함), new 플래그로 신규/재사용 구분
        assert len(stores) == 2
        assert [e.get("extra", {}).get("new") for e in stores] == [True, False]
        # 성공 + 실패(probing) reveal 모두 기록 (found 플래그)
        assert len(reveals) == 2
        assert {e.get("extra", {}).get("found") for e in reveals} == {True, False}
        # 성공 reveal 항목에 context 보존
        ok_reveal = next(e for e in reveals if e.get("extra", {}).get("found"))
        assert ok_reveal["context"] == "legitimate request"

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
