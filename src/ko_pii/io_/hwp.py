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


# HWP PARA_TEXT 제어문자 (UTF-16LE 코드포인트 0~31) — HWP 5.0 명세 + java-hwp 참조 구현 기준.
# inline ∪ extended controls 는 코드 1워드 + 14바이트(7워드) inline data → data 를 건너뛴다.
# (이전 구현은 5~8·12·14·15 등을 누락해 14바이트 payload 가 텍스트로 새어나왔고,
#  반대로 24~26 은 데이터 없는 char control 인데 14바이트를 더 소비해 정렬이 깨졌다.)
_CTRL_WITH_DATA = frozenset(
    {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
)
# 추가 데이터 없는 char control (0x0D=문단구분·0x09=탭은 _decode_para_text 에서 별도 처리)
_CTRL_NO_DATA = frozenset({0, 10, 24, 25, 26, 27, 28, 29, 30, 31})


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
        if cp == 0x0D:                 # 문단 구분 (char control, 데이터 없음)
            chars.append("\n")
            continue
        if cp == 0x09:                 # 탭 — inline control: \t + 14바이트 데이터
            chars.append("\t")
            i += 14
            continue
        if cp in _CTRL_WITH_DATA:      # inline/extended control: 14바이트 데이터 건너뜀
            i += 14
            continue
        if cp in _CTRL_NO_DATA:        # 데이터 없는 char control (0x00 포함)
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
