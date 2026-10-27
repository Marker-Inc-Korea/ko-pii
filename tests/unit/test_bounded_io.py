from __future__ import annotations

from pathlib import Path
import codecs
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


@pytest.mark.parametrize("name", ["max_file_bytes", "max_archive_members", "max_archive_member_bytes",
                                 "max_decompressed_bytes", "max_text_chars"])
@pytest.mark.parametrize("value", [0, -1, True, "10", 1.5, float("nan"), float("inf"), None])
def test_invalid_integer_limits_are_rejected(name, value):
    with pytest.raises(ValueError, match="positive integers"):
        FileReadPolicy(**{name: value})


@pytest.mark.parametrize("value", [True, "10", None, float("nan"), float("inf"), -float("inf"), 0.5,
                                 pytest.param(10**1000, id="integer-overflow")])
def test_invalid_ratio_is_rejected(value):
    with pytest.raises(ValueError, match="max_compression_ratio"):
        FileReadPolicy(max_compression_ratio=value)


@pytest.mark.parametrize("value", [".txt", 1, (None,), ("txt",)])
def test_invalid_extension_collection_is_rejected(value):
    with pytest.raises(ValueError, match="allowed_extensions"):
        FileReadPolicy(allowed_extensions=value)


def test_symlink_policy_requires_a_boolean():
    with pytest.raises(ValueError, match="reject_symlinks"):
        FileReadPolicy(reject_symlinks="false")


@pytest.mark.parametrize("isolated", [False, True])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16", "utf-16-le", "utf-16-be"])
@pytest.mark.parametrize("dtd", [True, False])
def test_xml_encoding_cannot_hide_dtd(tmp_path, isolated, encoding, dtd):
    from ko_pii.io_.isolated import read_text_isolated

    declaration = "UTF-16" if encoding.startswith("utf-16") else "UTF-8"
    content = "&contact;" if dtd else "first@example.com"
    doctype = '<!DOCTYPE p [<!ENTITY contact "first@example.com">]>' if dtd else ""
    text = f'<?xml version="1.0" encoding="{declaration}"?>{doctype}<p><t>{content}</t></p>'
    payload = text.encode(encoding)
    if encoding in {"utf-16-le", "utf-16-be"}:
        payload = (codecs.BOM_UTF16_LE if encoding.endswith("le") else codecs.BOM_UTF16_BE) + payload
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", payload)
    read = read_text_isolated if isolated else read_text_bounded
    if dtd:
        with pytest.raises(BoundedReadError) as exc:
            read(source)
        assert exc.value.code == "xml_dtd_rejected"
    else:
        assert read(source).text == "\nfirst@example.com"


def test_xml_validation_handles_chunk_boundaries_and_safe_literal_markers(tmp_path):
    source = tmp_path / "input.hwpx"
    prefix = "<!--" + "x" * 65525 + "-->"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", prefix + '<!DOCTYPE p><p><t>safe</t></p>')
    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)
    assert exc.value.code == "xml_dtd_rejected"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", '<p><t><![CDATA[<!DOCTYPE sample>]]></t></p>')
    assert read_text_bounded(source).text == "\n<!DOCTYPE sample>"


def test_invalid_xml_error_does_not_expose_source_content(tmp_path):
    source = tmp_path / "input.hwpx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", '<p><private-value></p>')
    with pytest.raises(BoundedReadError) as exc:
        read_text_bounded(source)
    assert exc.value.code == "document_extraction_incomplete"
    assert exc.value.coverage["status"] == "failed"
    assert "private-value" not in str(exc.value)
