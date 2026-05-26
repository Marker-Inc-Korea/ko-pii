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
