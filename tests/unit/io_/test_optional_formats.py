"""HWP 5.x · PDF 입력 — optional deps 가 있을 때만 실행."""
import pytest


class TestHwpOptional:
    def test_missing_olefile_raises_clear(self, tmp_path, monkeypatch):
        import sys
        # olefile import 가 안 된 상태 시뮬레이션
        from ko_pii.io_ import hwp as hwp_mod
        monkeypatch.setattr(hwp_mod, "_HAS_OLEFILE", False)
        with pytest.raises(ImportError, match="olefile"):
            hwp_mod.read_text(str(tmp_path / "dummy.hwp"))


class TestPdfOptional:
    def test_missing_pypdf_raises_clear(self, tmp_path, monkeypatch):
        from ko_pii.io_ import pdf as pdf_mod
        monkeypatch.setattr(pdf_mod, "_HAS_PYPDF", False)
        with pytest.raises(ImportError, match="pypdf"):
            pdf_mod.read_text(str(tmp_path / "dummy.pdf"))


class TestHwpWithOlefile:
    """실제 olefile 이 있을 때만 작동 — HWP 5.x 합성 파일은 만들기 복잡하므로
    record parser 단위 테스트만 한다."""

    def test_record_parser(self):
        from ko_pii.io_.hwp import _iter_records
        # 임의 레코드 2개 (tag=0x43 PARA_TEXT, body 4 bytes; tag=0x44 PARA_CHAR_SHAPE)
        import struct
        # tag=0x43 (67), level=0, size=4
        h1 = 0x43 | (0 << 10) | (4 << 20)
        # tag=0x44, level=0, size=2
        h2 = 0x44 | (0 << 10) | (2 << 20)
        stream = struct.pack("<I", h1) + b"\x41\x00\x42\x00" + struct.pack("<I", h2) + b"\x43\x00"
        records = list(_iter_records(stream))
        assert len(records) == 2
        assert records[0][0] == 0x43
        assert records[1][0] == 0x44

    def test_para_text_decoding(self):
        from ko_pii.io_.hwp import _decode_para_text
        # "Hi" in UTF-16LE
        body = b"\x48\x00\x69\x00"
        assert _decode_para_text(body) == "Hi"
        # 한글 "홍길동"
        text = "홍길동"
        body = text.encode("utf-16-le")
        assert _decode_para_text(body) == text
        # 0x0D (줄바꿈 control) — \n 으로 변환
        body = "A".encode("utf-16-le") + b"\x0D\x00" + "B".encode("utf-16-le")
        assert _decode_para_text(body) == "A\nB"
