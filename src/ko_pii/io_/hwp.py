"""HWP 5.x (구 한컴오피스, OLE 컴파운드) 텍스트 추출.

HWP 5.x 는 Microsoft OLE Compound Document 포맷 + 압축된 레코드 스트림.
HWPX 와 달리 XML 이 아니라 *바이너리 레코드* 라서 별도 파서 필요.

구조 (한컴테크 명세):
  - FileHeader (256 bytes) — 압축·암호화 플래그
  - DocInfo — 문서 메타
  - BodyText/Section0, Section1, ... — 본문 (zlib raw deflate 압축)
  - ViewText/Section0, ... — 미리보기 (선택)

각 섹션 스트림은 레코드의 연속:
  - Record header (4 bytes, little-endian):
      bits  0~9  (10 bits): tag ID
      bits 10~19 (10 bits): level (계층)
      bits 20~31 (12 bits): size
      size == 0xFFF 이면 다음 4 bytes 가 실제 size
  - Body (size bytes)

본문 텍스트는 ``HWPTAG_PARA_TEXT`` (0x43, 67) 레코드에 UTF-16LE 로 들어 있다.
일부 코드포인트 (0x00 ~ 0x1F) 는 inline control (각주·하이퍼링크·표 시작 등) 로
별도 의미 — 본 모듈은 *텍스트만* 추출하므로 control 은 건너뜀.

외부 의존성: ``olefile`` (BSD, ~50KB). ``pip install ko-pii[file]`` 로 설치.
"""
from __future__ import annotations

import struct
import zlib
from typing import Iterator

try:
    import olefile  # type: ignore
    _HAS_OLEFILE = True
except ImportError:
    _HAS_OLEFILE = False


# HWP record tag IDs (한컴테크 명세 5.0 기준)
HWPTAG_BEGIN = 0x010
HWPTAG_PARA_HEADER = HWPTAG_BEGIN + 50  # 0x42
HWPTAG_PARA_TEXT = HWPTAG_BEGIN + 51    # 0x43
HWPTAG_PARA_CHAR_SHAPE = HWPTAG_BEGIN + 52
HWPTAG_PARA_LINE_SEG = HWPTAG_BEGIN + 53


# HWP inline control codepoints — UTF-16LE 에서 이 값들은 단순 문자가 아니라
# 객체 (각주·표·하이퍼링크 등) 의 anchor. 8 char (16 byte) 의 extended data 가
# 뒤따른다 — 텍스트 추출 시 건너뜀.
_INLINE_CONTROL_CODES = frozenset({
    0x01,  # extended (object)
    0x02,  # section column def
    0x03,  # field begin
    0x04,  # field end
    0x05,  # ?
    0x06,  # bookmark
    0x07,  # date
    0x08,  # date format
    0x09,  # tab (실제 줄바꿈)  — 보존
    0x0A,  # ?
    0x0B,  # drawing/table
    0x0C,  # ?
    0x0D,  # paragraph break — 줄바꿈 보존
    0x0E,  # ?
    0x0F,  # hidden info
    0x10,  # header/footer
    0x11,  # footnote
    0x12,  # auto number
    0x13,  # new number
    0x14,  # page hide
    0x15,  # page oddeven adjustment
    0x16,  # page number position
    0x17,  # ?
    0x18,  # column def
    0x19,  # hyperlink
    0x1A,  # additional info
    0x1B,  # ?
    0x1C,  # ?
    0x1D,  # ?
    0x1E,  # ?
    0x1F,  # ?
})


def _ensure_olefile() -> None:
    if not _HAS_OLEFILE:
        raise ImportError(
            "HWP 5.x 입력은 'olefile' 패키지가 필요합니다.\n"
            "  pip install ko-pii[file]\n"
            "또는 pip install olefile"
        )


def _iter_records(stream: bytes) -> Iterator[tuple[int, int, bytes]]:
    """Iterate HWP records: yields ``(tag_id, level, body)``."""
    i = 0
    n = len(stream)
    while i + 4 <= n:
        header = struct.unpack_from("<I", stream, i)[0]
        i += 4
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if i + 4 > n:
                break
            size = struct.unpack_from("<I", stream, i)[0]
            i += 4
        if i + size > n:
            break
        body = stream[i:i + size]
        i += size
        yield tag_id, level, body


def _decode_para_text(body: bytes) -> str:
    """Decode a PARA_TEXT body — UTF-16LE characters + inline controls."""
    chars: list[str] = []
    i = 0
    n = len(body)
    while i + 2 <= n:
        cp = struct.unpack_from("<H", body, i)[0]
        i += 2
        if cp in _INLINE_CONTROL_CODES:
            if cp == 0x0D:
                chars.append("\n")
            elif cp == 0x09:
                chars.append("\t")
            # extended control 은 14 bytes 더 따라옴
            if cp in {0x01, 0x02, 0x03, 0x04, 0x0B, 0x10, 0x11, 0x12,
                      0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A}:
                i += 14
            continue
        if cp == 0x00:
            continue
        try:
            chars.append(chr(cp))
        except ValueError:
            continue
    return "".join(chars)


def _is_compressed(header_bytes: bytes) -> bool:
    """HWP FileHeader byte 36 의 bit 0 이 압축 플래그."""
    if len(header_bytes) < 37:
        return True  # 안전한 기본값
    return bool(header_bytes[36] & 0x01)


def read_text(path: str) -> str:
    _ensure_olefile()
    ole = olefile.OleFileIO(path)
    try:
        # FileHeader 로 압축 여부 판단
        try:
            header_bytes = ole.openstream("FileHeader").read()
        except Exception:
            header_bytes = b""
        compressed = _is_compressed(header_bytes)

        # Section streams
        section_paths = sorted(
            p for p in ole.listdir() if p and p[0] == "BodyText"
        )
        out: list[str] = []
        for path_parts in section_paths:
            try:
                raw = ole.openstream(path_parts).read()
            except Exception:
                continue
            if compressed:
                try:
                    raw = zlib.decompress(raw, -15)  # raw deflate
                except zlib.error:
                    continue
            for tag_id, _level, body in _iter_records(raw):
                if tag_id == HWPTAG_PARA_TEXT:
                    out.append(_decode_para_text(body))
                    out.append("\n")
            out.append("\n")  # section separator
        return "".join(out)
    finally:
        ole.close()
