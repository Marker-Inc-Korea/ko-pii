"""Bounded document extraction for untrusted ingestion paths."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import NoReturn
import zipfile

from ko_pii.io_ import dispatcher


DEFAULT_BOUNDED_EXTENSIONS: tuple[str, ...] = (
    ".txt",
    ".md",
    ".log",
    ".csv",
    ".tsv",
    ".hwpx",
    ".docx",
    ".xlsx",
)
_ZIP_EXTENSIONS = frozenset({".hwpx", ".docx", ".xlsx"})
_BINARY_EXTENSIONS = _ZIP_EXTENSIONS | {".pdf", ".hwp"}
_OLE_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")


class BoundedReadError(ValueError):
    """Machine-readable rejection raised before content reaches a guard."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FileReadPolicy:
    """Resource and format limits for one untrusted document."""

    max_file_bytes: int = 16 * 1024 * 1024
    max_archive_members: int = 2_048
    max_archive_member_bytes: int = 16 * 1024 * 1024
    max_decompressed_bytes: int = 64 * 1024 * 1024
    max_compression_ratio: float = 200.0
    max_text_chars: int = 2_000_000
    allowed_extensions: tuple[str, ...] = DEFAULT_BOUNDED_EXTENSIONS
    reject_symlinks: bool = True

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_file_bytes,
            self.max_archive_members,
            self.max_archive_member_bytes,
            self.max_decompressed_bytes,
            self.max_text_chars,
        )
        if any(value < 1 for value in integer_limits):
            raise ValueError("all bounded-read limits must be positive")
        if self.max_compression_ratio < 1.0:
            raise ValueError("max_compression_ratio must be at least 1.0")
        if not self.allowed_extensions:
            raise ValueError("allowed_extensions must not be empty")
        if any(not value.startswith(".") for value in self.allowed_extensions):
            raise ValueError("allowed_extensions entries must start with '.'")


@dataclass(frozen=True)
class BoundedDocument:
    """Extracted text plus provenance that contains no document content."""

    text: str
    sha256: str
    size_bytes: int
    extension: str
    archive_members: int = 0
    declared_decompressed_bytes: int = 0


def _reject(code: str, message: str) -> NoReturn:
    raise BoundedReadError(code, message)


def _validate_path(path: Path, policy: FileReadPolicy) -> tuple[os.stat_result, str]:
    if policy.reject_symlinks and path.is_symlink():
        _reject("symlink_rejected", "symbolic links are not accepted")
    try:
        before = path.stat(follow_symlinks=not policy.reject_symlinks)
    except (FileNotFoundError, OSError):
        _reject("file_unavailable", "document is not an accessible file")
    if not stat.S_ISREG(before.st_mode):
        _reject("not_regular_file", "document must be a regular file")
    if before.st_size > policy.max_file_bytes:
        _reject("file_too_large", "document exceeds max_file_bytes")
    extension = path.suffix.casefold()
    allowed = {value.casefold() for value in policy.allowed_extensions}
    if extension not in allowed:
        _reject("unsupported_extension", "document extension is not allowed")
    return before, extension


def _validate_signature(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        prefix = handle.read(8)
    if extension in _ZIP_EXTENSIONS:
        if not zipfile.is_zipfile(path):
            _reject("format_mismatch", "archive extension does not match file content")
    elif extension == ".pdf" and not prefix.startswith(b"%PDF-"):
        _reject("format_mismatch", "PDF extension does not match file content")
    elif extension == ".hwp" and prefix != _OLE_SIGNATURE:
        _reject("format_mismatch", "HWP extension does not match file content")
    elif extension not in {".pdf", ".hwp"} and b"\x00" in prefix:
        _reject("format_mismatch", "text input contains a binary signature")


def _safe_archive_name(name: str) -> str:
    normalized = name.replace("\\", "/")
    parsed = PurePosixPath(normalized)
    if (
        not normalized
        or parsed.is_absolute()
        or ".." in parsed.parts
        or (parsed.parts and ":" in parsed.parts[0])
    ):
        _reject("unsafe_archive_path", "archive contains an unsafe member path")
    return normalized


def _validate_archive(
    path: Path,
    extension: str,
    policy: FileReadPolicy,
) -> tuple[int, int]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > policy.max_archive_members:
                _reject("too_many_archive_members", "archive member count exceeds policy")

            names: set[str] = set()
            xml_infos: list[zipfile.ZipInfo] = []
            total = 0
            for info in infos:
                name = _safe_archive_name(info.filename)
                if name in names:
                    _reject("duplicate_archive_member", "archive contains duplicate members")
                names.add(name)
                if info.flag_bits & 0x1:
                    _reject("encrypted_archive", "encrypted archive members are not accepted")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    _reject("archive_symlink", "archive symlinks are not accepted")
                if info.file_size > policy.max_archive_member_bytes:
                    _reject("archive_member_too_large", "archive member exceeds policy")
                total += info.file_size
                if total > policy.max_decompressed_bytes:
                    _reject("archive_too_large", "declared decompressed size exceeds policy")
                if info.file_size > 1_024:
                    if info.compress_size == 0:
                        _reject("compression_ratio_exceeded", "archive member has zero compressed size")
                    ratio = info.file_size / info.compress_size
                    if ratio > policy.max_compression_ratio:
                        _reject("compression_ratio_exceeded", "archive compression ratio exceeds policy")
                if name.casefold().endswith((".xml", ".rels")):
                    xml_infos.append(info)

            # OOXML and HWPX do not require DTDs. Reject them before ElementTree
            # sees the payload so internal entity expansion cannot amplify a
            # small, otherwise valid archive member in parser memory.
            for info in xml_infos:
                xml_upper = archive.read(info).upper()
                if b"<!DOCTYPE" in xml_upper or b"<!ENTITY" in xml_upper:
                    _reject(
                        "xml_dtd_rejected",
                        "archive XML contains a DTD or entity declaration",
                    )

            if extension == ".docx" and "word/document.xml" not in names:
                _reject("format_mismatch", "DOCX archive is missing word/document.xml")
            if extension == ".xlsx" and "xl/workbook.xml" not in names:
                _reject("format_mismatch", "XLSX archive is missing xl/workbook.xml")
            if extension == ".hwpx" and not any(
                name.startswith("Contents/section") and name.endswith(".xml")
                for name in names
            ):
                _reject("format_mismatch", "HWPX archive has no section XML")
            return len(infos), total
    except BoundedReadError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError):
        _reject("invalid_archive", "document archive is invalid")


def _sha256(path: Path, *, reject_nul: bool = False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            if reject_nul and b"\x00" in block:
                _reject("format_mismatch", "text input contains a NUL byte")
            digest.update(block)
    return digest.hexdigest()


def read_text_bounded(
    path: str | Path,
    *,
    policy: FileReadPolicy | None = None,
) -> BoundedDocument:
    """Validate resource bounds, extract text, and return safe provenance.

    Legacy HWP and PDF are excluded from the default allowlist because their
    optional parsers do not expose a deterministic decompression/page budget.
    Deployments may opt in only when extraction runs in a separately constrained
    worker or container.
    """

    active_policy = policy or FileReadPolicy()
    source = Path(path)
    before, extension = _validate_path(source, active_policy)
    _validate_signature(source, extension)
    members = 0
    decompressed = 0
    if extension in _ZIP_EXTENSIONS:
        members, decompressed = _validate_archive(source, extension, active_policy)
    source_digest = _sha256(
        source,
        reject_nul=extension not in _BINARY_EXTENSIONS,
    )
    try:
        text = dispatcher.read_text(str(source))
    except ImportError:
        _reject("extractor_unavailable", "required document extractor is unavailable")
    except BoundedReadError:
        raise
    except Exception:
        _reject("extract_failed", "document text extraction failed")
    if len(text) > active_policy.max_text_chars:
        _reject("extracted_text_too_large", "extracted text exceeds max_text_chars")

    try:
        after = source.stat(follow_symlinks=not active_policy.reject_symlinks)
    except OSError:
        _reject("source_changed", "document changed during extraction")
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or _sha256(source) != source_digest:
        _reject("source_changed", "document changed during extraction")

    return BoundedDocument(
        text=text,
        sha256=source_digest,
        size_bytes=before.st_size,
        extension=extension,
        archive_members=members,
        declared_decompressed_bytes=decompressed,
    )
