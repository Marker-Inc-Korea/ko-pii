from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

from ko_pii.cli import main
from ko_pii.io_.atomic import write_bytes_atomic
from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy
from ko_pii.io_.isolated import read_text_isolated
from ko_pii.vault.reversible import ReversibleVault


@pytest.mark.parametrize("kind", ["plain", "encrypted"])
def test_failed_vault_replace_preserves_previous_file(tmp_path, monkeypatch, kind):
    vault = ReversibleVault()
    vault.store("PHONE", "010-1234-5678", 4)
    target = tmp_path / "vault"
    target.write_bytes(b"previous vault")

    def fail_replace(*args):
        raise OSError("storage failure")

    monkeypatch.setattr("ko_pii.io_.atomic.os.replace", fail_replace)
    with pytest.raises(OSError, match="storage failure"):
        if kind == "encrypted":
            pytest.importorskip("cryptography")
            from ko_pii.vault.encrypted import save_encrypted
            save_encrypted(vault, str(target), "test-password")
        else:
            vault.save(str(target))
    assert target.read_bytes() == b"previous vault"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_files_are_private_and_symlinks_are_not_followed(tmp_path):
    target = tmp_path / "vault"
    write_bytes_atomic(target, b"state")
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        write_bytes_atomic(link, b"changed")
    assert target.read_bytes() == b"state"


def test_cli_does_not_publish_when_vault_storage_fails(tmp_path, monkeypatch, capsys):
    source = tmp_path / "in.txt"
    source.write_text("연락처 010-1234-5678", encoding="utf-8")

    def fail_save(*args):
        raise OSError("vault unavailable")

    monkeypatch.setattr("ko_pii.cli._save_vault", fail_save)
    with pytest.raises(OSError, match="vault unavailable"):
        main([str(source), "--vault", str(tmp_path / "vault")])
    assert capsys.readouterr().out == ""


def test_cli_password_is_requested_once_for_load_and_save(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from ko_pii.vault.encrypted import load_encrypted, save_encrypted
    source = tmp_path / "in.txt"
    source.write_text("연락처 010-1234-5678", encoding="utf-8")
    vault = tmp_path / "vault"
    save_encrypted(ReversibleVault(), str(vault), "test-password")
    prompts = []

    def password(prompt):
        prompts.append(prompt)
        return "test-password"

    monkeypatch.setattr("getpass.getpass", password)
    assert main([str(source), "--vault", str(vault), "--vault-password"]) == 0
    assert len(prompts) == 1
    assert load_encrypted(str(vault), "test-password").reveal("<PHONE_1>") == "010-1234-5678"


@pytest.mark.parametrize("option", ["--vault", "--output", "--report", "--audit-log"])
def test_cli_rejects_paths_aliasing_input(tmp_path, option):
    source = tmp_path / "in.txt"
    source.write_text("original", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(source), option, str(source)])
    assert exc.value.code == 2
    assert source.read_text() == "original"


def test_cli_rejects_hardlinked_outputs(tmp_path):
    source = tmp_path / "in.txt"
    source.write_text("original", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.write_text("state")
    output = tmp_path / "out.txt"
    os.link(vault, output)
    with pytest.raises(SystemExit):
        main([str(source), "--vault", str(vault), "-o", str(output)])


def test_isolated_reader_round_trip_and_size_limit(tmp_path):
    source = tmp_path / "in.txt"
    source.write_text("문서 내용", encoding="utf-8")
    assert read_text_isolated(source).text == "문서 내용"
    with pytest.raises(BoundedReadError) as exc:
        read_text_isolated(source, policy=FileReadPolicy(max_file_bytes=2))
    assert exc.value.code == "file_too_large"


def test_extraction_timeout_terminates_worker(monkeypatch):
    real_run = subprocess.run

    def slow_worker(*args, **kwargs):
        return real_run([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)

    monkeypatch.setattr("ko_pii.io_.isolated.subprocess.run", slow_worker)
    with pytest.raises(BoundedReadError) as exc:
        read_text_isolated("unused", timeout=0.1)
    assert exc.value.code == "extract_timeout"


def test_cli_limits_report_json_without_publishing(tmp_path, capsys):
    source = tmp_path / "in.txt"
    source.write_text("oversized")
    output = tmp_path / "out.txt"
    assert main([str(source), "--max-file-bytes", "2", "-o", str(output), "--json-summary"]) == 1
    payload = json.loads(capsys.readouterr().err)
    assert payload["error"] == "file_too_large"
    assert not output.exists()


def test_cli_stdin_is_bounded(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("가나다라"))
    assert main(["-", "--max-file-bytes", "3", "--json-summary"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err)["error"] == "stdin_too_large"


def test_batch_rejects_zip_expansion_without_output(tmp_path, capsys):
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", "A" * 20_000)
    output = tmp_path / "out"
    rc = main([str(source), "--batch", "--output-dir", str(output), "--json-summary"])
    assert rc == 1
    result = json.loads(capsys.readouterr().err)["results"][0]
    assert result["error_code"] == "compression_ratio_exceeded"
    assert not output.exists()


def test_cli_batch_output_ancestor_returns_failure_json(tmp_path, capsys):
    inputs = tmp_path / "in"
    inputs.mkdir()
    (inputs / "doc.txt").write_text("original")
    assert main([str(inputs), "--batch", "--output-dir", str(tmp_path), "--json-summary"]) == 1
    assert json.loads(capsys.readouterr().err)["error"] == "batch_configuration"


def test_scanned_pdf_requires_review_in_real_worker(tmp_path, capsys):
    pypdf = pytest.importorskip("pypdf")
    source = tmp_path / "scan.pdf"
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with source.open("wb") as handle:
        writer.write(handle)
    assert main([str(source), "--json-summary"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["error"] == "pdf_extraction_incomplete"
    assert "empty_pages=[1]" in payload["message"]
