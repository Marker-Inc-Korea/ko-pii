"""Exercise installed CLI/worker processes from outside the source tree."""
import json
import os
import subprocess
import sys
import zipfile

import pytest


def run_cli(directory, *args, **environment):
    env = {**os.environ, "PYTHONUTF8": "1", **environment}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, "-m", "ko_pii.cli", *args], cwd=directory,
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_installed_cli_worker_and_private_vault_round_trip(tmp_path):
    pytest.importorskip("cryptography")
    from ko_pii.vault.encrypted import load_encrypted
    source = tmp_path / "sample.docx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("word/document.xml", "<document><p><t>010-1234-5678</t></p></document>")
    vault = tmp_path / "vault.kvault"
    for _ in range(2):
        result = run_cli(tmp_path, str(source), "--vault", str(vault), "--json-summary", KPII_VAULT_PASSWORD="test-only-password")
        assert result.returncode == 0, result.stderr
        assert "010-1234-5678" not in result.stdout
        assert "<PHONE_1>" in result.stdout
        assert json.loads(result.stderr)["extraction_coverage"]["status"] == "complete"
    assert load_encrypted(str(vault), "test-only-password").reveal("<PHONE_1>") == "010-1234-5678"
    if os.name == "posix":
        assert vault.stat().st_mode & 0o777 == 0o600


def test_installed_batch_worker_failure_and_parallel_success(tmp_path):
    source = tmp_path / "in"
    source.mkdir()
    (source / "valid.txt").write_text("010-1234-5678", encoding="utf-8")
    (source / "bad.docx").write_bytes(b"invalid zip")
    output = tmp_path / "out"
    result = run_cli(tmp_path, str(source), "--batch", "--workers", "2", "--output-dir", str(output), "--json-summary")
    assert result.returncode == 1, result.stderr
    summary = json.loads(result.stderr)
    assert summary["succeeded"] == summary["failed"] == 1
    assert "010-1234-5678" not in (output / "valid.txt").read_text(encoding="utf-8")
    assert not (output / "bad.txt").exists()
