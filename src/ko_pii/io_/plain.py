"""Plain text decoding: UTF-8 (including BOM), then lossless Korean fallbacks."""
from __future__ import annotations

import codecs


class TextDecodingError(ValueError):
    """No supported codec can read the file without discarding source bytes."""

    code = "text_decode_failed"


def read_text(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    # Consume a file-level UTF-8 signature before CSV interprets its first header.
    # A declared UTF-8 file must not be silently reinterpreted as a legacy codec.
    encodings = ("utf-8-sig",) if raw.startswith(codecs.BOM_UTF8) else ("utf-8", "cp949", "euc-kr")
    for enc in encodings:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise TextDecodingError("text cannot be decoded as supported UTF-8/CP949/EUC-KR without data loss")
