from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from ko_pii.io_ import (
    BoundedReadError,
    FileReadPolicy,
    read_text_bounded,
)


def test_reads_plain_text_with_content_free_provenance(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_text("민원 처리 문서", encoding="utf-8")

    result = read_text_bounded(source)

    assert result.text == "민원 처리 문서"
    assert result.size_bytes == len(source.read_bytes())
    assert len(result.sha256) == 64
    assert result.archive_members == 0


def test_rejects_oversized_file_before_extraction(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_text("1234", encoding="utf-8")

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source, policy=FileReadPolicy(max_file_bytes=3))

    assert exc.value.code == "file_too_large"


def test_rejects_symlink(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("safe", encoding="utf-8")
    source = tmp_path / "input.txt"
    source.symlink_to(target)

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "symlink_rejected"


def test_explicit_policy_can_follow_symlink(tmp_path: Path):
    target = tmp_path / "target.txt"
    target.write_text("safe", encoding="utf-8")
    source = tmp_path / "input.txt"
    source.symlink_to(target)

    result = read_text_bounded(
        source,
        policy=FileReadPolicy(reject_symlinks=False),
    )

    assert result.text == "safe"


def test_rejects_binary_content_with_text_extension(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_bytes(b"text\x00binary")

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "format_mismatch"


def test_rejects_nul_after_signature_prefix(tmp_path: Path):
    source = tmp_path / "input.txt"
    source.write_bytes(b"ordinary text prefix\x00binary tail")

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "format_mismatch"


def test_reads_preflighted_hwpx(tmp_path: Path):
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", "<p><t>안전한 문서</t></p>")

    result = read_text_bounded(source)

    assert "안전한 문서" in result.text
    assert result.archive_members == 1
    assert result.declared_decompressed_bytes > 0


def test_rejects_archive_path_traversal(tmp_path: Path):
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", "<p><t>본문</t></p>")
        archive.writestr("../escape.txt", "escape")

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "unsafe_archive_path"


def test_rejects_excessive_compression_ratio(tmp_path: Path):
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", "A" * 20_000)

    policy = FileReadPolicy(max_compression_ratio=2.0)
    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source, policy=policy)

    assert exc.value.code == "compression_ratio_exceeded"


def test_rejects_archive_xml_dtd_before_parsing(tmp_path: Path):
    source = tmp_path / "input.hwpx"
    xml = "<!DOCTYPE p [<!ENTITY x 'expanded'>]><p><t>&x;</t></p>"
    with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", xml)

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "xml_dtd_rejected"


def test_legacy_parser_formats_require_explicit_opt_in(tmp_path: Path):
    source = tmp_path / "input.pdf"
    source.write_bytes(b"%PDF-1.7\n")

    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)

    assert exc.value.code == "unsupported_extension"
