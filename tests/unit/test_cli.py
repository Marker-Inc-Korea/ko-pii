import json
import os

import pytest

from ko_pii.cli import main
from ko_pii.vault.reversible import ReversibleVault


def _write(p, text):
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def test_cli_tokenize_writes_output_and_vault(tmp_path, capsys):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    vault = tmp_path / "vault.json"
    _write(src, "신청인 880101-1234568")

    rc = main([
        str(src), "-m", "STRICT", "-s", "tokenize",
        "-o", str(out), "--vault", str(vault),
    ])
    assert rc == 0
    body = _read(out)
    assert "<RRN_1>" in body
    assert "880101-1234568" not in body
    # Vault saved
    assert os.path.exists(vault)
    v = ReversibleVault.load(str(vault))
    assert v.reveal("<RRN_1>") == "880101-1234568"
    assert "원본 개인정보가 평문" in capsys.readouterr().err


def test_cli_redact_strategy(tmp_path):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "연락처 010-1234-5678")
    rc = main([str(src), "-s", "redact", "-o", str(out)])
    assert rc == 0
    assert "[전화번호]" in _read(out)


def test_cli_json_summary(tmp_path, capsys):
    src = tmp_path / "in.txt"
    _write(src, "신청인 880101-1234568")
    main([str(src), "-o", str(tmp_path / "out.txt"), "--json-summary"])
    err = capsys.readouterr().err
    payload = json.loads(err)
    assert payload["total"] >= 1
    assert payload["mode"] == "STRICT"


def test_cli_json_summary_keeps_plaintext_vault_warning_parseable(
    tmp_path, capsys
):
    src = tmp_path / "in.txt"
    vault = tmp_path / "vault.json"
    _write(src, "신청인 880101-1234568")

    rc = main([
        str(src),
        "-o", str(tmp_path / "out.txt"),
        "--vault", str(vault),
        "--json-summary",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().err)
    assert payload["total"] >= 1
    assert any("원본 개인정보가 평문" in item for item in payload["warnings"])


def test_cli_batch_json_summary_is_the_only_stderr_payload(tmp_path, capsys):
    src = tmp_path / "in"
    src.mkdir()
    _write(src / "one.txt", "연락처 010-1234-5678")

    rc = main([
        str(src),
        "--batch",
        "--output-dir", str(tmp_path / "out"),
        "--json-summary",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().err)
    assert payload["total"] == 1
    assert payload["succeeded"] == 1


def test_cli_certificate_report(tmp_path):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    report = tmp_path / "report.txt"
    _write(src, "신청인 880101-1234568")
    main([str(src), "-o", str(out), "--report", str(report)])
    assert os.path.exists(report)
    content = _read(report)
    assert "처리 증명서" in content


def test_cli_include_filter(tmp_path):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568 연락처 010-1234-5678")
    main([str(src), "-s", "redact", "-o", str(out), "--include", "RRN"])
    body = _read(out)
    assert "[주민등록번호]" in body
    assert "010-1234-5678" in body  # not filtered


def test_cli_person_exclusions_file(tmp_path):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    exclusions = tmp_path / "person-exclusions.txt"
    _write(src, "성명: 김도구")
    _write(exclusions, "# tenant vocabulary\n\n김도구\n")

    rc = main([
        str(src),
        "-s", "redact",
        "-o", str(out),
        "--person-exclusions-file", str(exclusions),
    ])

    assert rc == 0
    assert _read(out) == "성명: 김도구"


def test_cli_audit_is_fail_closed_by_default_and_closes_log(
    tmp_path, monkeypatch
):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")
    instances = []

    class FailingAudit:
        def __init__(self, path):
            self.closed = False
            instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def record_store(self, *args, **kwargs):
            raise OSError("audit unavailable")

        def record_reveal(self, *args, **kwargs):
            raise OSError("audit unavailable")

        def record_anonymize(self, *args, **kwargs):
            pass

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingAudit)

    with pytest.raises(OSError, match="audit unavailable"):
        main([str(src), "-o", str(out), "--audit-log", str(tmp_path / "audit")])

    assert not out.exists()
    assert instances[0].closed is True


def test_cli_can_opt_into_best_effort_audit(tmp_path, monkeypatch, capsys):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")

    class FailingStoreAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise OSError("audit close unavailable")

        def record_store(self, *args, **kwargs):
            raise OSError("audit unavailable")

        def record_reveal(self, *args, **kwargs):
            raise OSError("audit unavailable")

        def record_anonymize(self, *args, **kwargs):
            raise OSError("audit unavailable")

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingStoreAudit)

    rc = main([
        str(src),
        "-o", str(out),
        "--audit-log", str(tmp_path / "audit"),
        "--audit-failure-policy", "best_effort",
        "--json-summary",
    ])

    assert rc == 0
    assert "<RRN_1>" in _read(out)
    payload = json.loads(capsys.readouterr().err)
    assert any("감사 레코드를 기록하지 못했습니다" in w for w in payload["warnings"])
    assert any("감사 로그를 정상적으로 종료하지 못했" in w for w in payload["warnings"])


def test_cli_best_effort_continues_when_audit_log_cannot_open(
    tmp_path, monkeypatch, capsys
):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")

    class FailingOpenAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            raise OSError("audit path unavailable")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingOpenAudit)

    rc = main([
        str(src),
        "-o", str(out),
        "--audit-log", str(tmp_path / "missing" / "audit.jsonl"),
        "--audit-failure-policy", "best_effort",
        "--json-summary",
    ])

    assert rc == 0
    assert "<RRN_1>" in _read(out)
    payload = json.loads(capsys.readouterr().err)
    assert any("감사 로그를 열지 못해" in item for item in payload["warnings"])


def test_cli_audit_open_failure_is_fail_closed_by_default(tmp_path, monkeypatch):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")

    class FailingOpenAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            raise OSError("audit path unavailable")

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingOpenAudit)

    with pytest.raises(OSError, match="audit path unavailable"):
        main([
            str(src),
            "-o", str(out),
            "--audit-log", str(tmp_path / "missing" / "audit.jsonl"),
        ])

    assert not out.exists()


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--audit-log", "state"),
        ("--audit-log", ""),
        ("--vault", "state"),
        ("--vault", ""),
        ("--vault-password", "state"),
        ("--vault-password", ""),
    ],
)
def test_cli_batch_rejects_unsupported_security_state_options(
    tmp_path, option, value, capsys
):
    src = tmp_path / "in"
    src.mkdir()
    _write(src / "one.txt", "연락처 010-1234-5678")

    with pytest.raises(SystemExit, match="2"):
        main([
            str(src),
            "--batch",
            option, value,
        ])

    assert option in capsys.readouterr().err
    assert not (tmp_path / "anon").exists()


def test_cli_json_summary_rejects_interactive_password_prompt(
    tmp_path, monkeypatch, capsys
):
    src = tmp_path / "in.txt"
    _write(src, "주민번호 880101-1234568")

    def unexpected_prompt(prompt):
        raise AssertionError(f"unexpected password prompt: {prompt}")

    monkeypatch.setattr("getpass.getpass", unexpected_prompt)

    with pytest.raises(SystemExit, match="2"):
        main([
            str(src),
            "--vault", str(tmp_path / "vault.kvault"),
            "--vault-password",
            "--json-summary",
        ])

    assert "KPII_VAULT_PASSWORD" in capsys.readouterr().err


def test_cli_strict_audit_close_failure_prevents_output(tmp_path, monkeypatch):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")

    class FailingCloseAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            raise OSError("audit close unavailable")

        def record_store(self, *args, **kwargs):
            pass

        def record_reveal(self, *args, **kwargs):
            pass

        def record_anonymize(self, *args, **kwargs):
            pass

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingCloseAudit)

    with pytest.raises(OSError, match="audit close unavailable"):
        main([
            str(src),
            "-o", str(out),
            "--audit-log", str(tmp_path / "audit.jsonl"),
        ])

    assert not out.exists()


def test_cli_audit_marks_prepared_not_persisted_before_output(
    tmp_path, monkeypatch
):
    src = tmp_path / "in.txt"
    _write(src, "주민번호 880101-1234568")
    events = []

    class RecordingAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def record_store(self, *args, **kwargs):
            pass

        def record_reveal(self, *args, **kwargs):
            pass

        def record_anonymize(self, *args, **kwargs):
            events.append(kwargs)

    def failing_output(path, text):
        raise OSError("output unavailable")

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", RecordingAudit)
    monkeypatch.setattr("ko_pii.cli._write_output", failing_output)

    with pytest.raises(OSError, match="output unavailable"):
        main([
            str(src),
            "-o", str(tmp_path / "out.txt"),
            "--audit-log", str(tmp_path / "audit.jsonl"),
        ])

    assert events == [{
        "count": 1,
        "mode": "STRICT",
        "status": "prepared",
        "context": str(src),
    }]


def test_cli_summary_audit_failure_prevents_output_in_strict_mode(
    tmp_path, monkeypatch
):
    src = tmp_path / "in.txt"
    out = tmp_path / "out.txt"
    _write(src, "주민번호 880101-1234568")

    class FailingSummaryAudit:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def record_store(self, *args, **kwargs):
            pass

        def record_reveal(self, *args, **kwargs):
            pass

        def record_anonymize(self, *args, **kwargs):
            raise OSError("audit summary unavailable")

    monkeypatch.setattr("ko_pii.vault.audit.AuditLog", FailingSummaryAudit)

    with pytest.raises(OSError, match="audit summary unavailable"):
        main([
            str(src),
            "-s", "redact",
            "-o", str(out),
            "--audit-log", str(tmp_path / "audit"),
        ])

    assert not out.exists()
