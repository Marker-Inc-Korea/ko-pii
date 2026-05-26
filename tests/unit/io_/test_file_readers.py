"""파일 reader 테스트 — stdlib 만으로 HWPX/DOCX/XLSX/CSV/TXT 처리.

각 테스트는 in-memory ZIP 파일을 만들고 reader 가 텍스트를 정확히 추출하는지 검증.
"""
from __future__ import annotations

import zipfile

import pytest

from ko_pii.io_ import read_text, read_records


# ─────────────────────────────────────────────────────────────────────
# 평문 (plain text)
# ─────────────────────────────────────────────────────────────────────

class TestPlainText:
    def test_utf8(self, tmp_path):
        p = tmp_path / "doc.txt"
        p.write_text("안녕하세요\n주민번호: 880101-1234568", encoding="utf-8")
        assert "주민번호" in read_text(str(p))

    def test_cp949_fallback(self, tmp_path):
        p = tmp_path / "doc.txt"
        p.write_bytes("한국어 텍스트".encode("cp949"))
        assert "한국어" in read_text(str(p))


# ─────────────────────────────────────────────────────────────────────
# CSV / TSV
# ─────────────────────────────────────────────────────────────────────

class TestCsv:
    def test_basic_csv(self, tmp_path):
        p = tmp_path / "users.csv"
        p.write_text(
            "성명,주민번호,연락처\n홍길동,880101-1234568,010-1234-5678\n",
            encoding="utf-8",
        )
        text = read_text(str(p))
        assert "홍길동" in text
        records = read_records(str(p))
        assert len(records) == 1
        assert records[0]["성명"] == "홍길동"
        assert records[0]["주민번호"] == "880101-1234568"

    def test_tsv(self, tmp_path):
        p = tmp_path / "users.tsv"
        p.write_text(
            "성명\t주민번호\n홍길동\t880101-1234568\n",
            encoding="utf-8",
        )
        records = read_records(str(p))
        assert records[0]["성명"] == "홍길동"


# ─────────────────────────────────────────────────────────────────────
# HWPX (합성)
# ─────────────────────────────────────────────────────────────────────

def _make_hwpx(path, paragraphs: list[str]):
    NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    runs = "".join(
        f'<hp:p xmlns:hp="{NS}"><hp:run><hp:t>{p}</hp:t></hp:run></hp:p>'
        for p in paragraphs
    )
    section = f'<?xml version="1.0" encoding="UTF-8"?><hp:sec xmlns:hp="{NS}">{runs}</hp:sec>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("META-INF/manifest.xml", "<manifest/>")
        zf.writestr("Contents/section0.xml", section)


class TestHwpx:
    def test_basic_extraction(self, tmp_path):
        p = tmp_path / "doc.hwpx"
        _make_hwpx(p, [
            "기획재정부 결재공문",
            "신청인 홍길동",
            "주민등록번호: 880101-1234568",
        ])
        text = read_text(str(p))
        assert "홍길동" in text
        assert "880101-1234568" in text
        assert "기획재정부" in text


# ─────────────────────────────────────────────────────────────────────
# DOCX (합성)
# ─────────────────────────────────────────────────────────────────────

def _make_docx(path, paragraphs: list[str]):
    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paras = "".join(
        f'<w:p xmlns:w="{W}"><w:r><w:t>{p}</w:t></w:r></w:p>'
        for p in paragraphs
    )
    doc = f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>{paras}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml", doc)


class TestDocx:
    def test_basic_extraction(self, tmp_path):
        p = tmp_path / "doc.docx"
        _make_docx(p, [
            "인사 평가서",
            "성명: 홍길동",
            "연락처: 010-1234-5678",
        ])
        text = read_text(str(p))
        assert "홍길동" in text
        assert "010-1234-5678" in text


# ─────────────────────────────────────────────────────────────────────
# XLSX (합성)
# ─────────────────────────────────────────────────────────────────────

def _make_xlsx(path, rows: list[list[str]]):
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    # Build shared strings
    unique: list[str] = []
    for r in rows:
        for c in r:
            if c not in unique:
                unique.append(c)
    sst_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<sst xmlns="{NS}" count="{sum(len(r) for r in rows)}" '
        f'uniqueCount="{len(unique)}">'
        + "".join(f"<si><t>{s}</t></si>" for s in unique)
        + "</sst>"
    )

    def cell_xml(col: int, row_num: int, val: str) -> str:
        idx = unique.index(val)
        col_letter = chr(ord("A") + col)
        return f'<c r="{col_letter}{row_num}" t="s"><v>{idx}</v></c>'

    row_xml = "".join(
        f'<row r="{i+1}">{ "".join(cell_xml(j, i+1, c) for j, c in enumerate(r)) }</row>'
        for i, r in enumerate(rows)
    )
    sheet_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<worksheet xmlns="{NS}"><sheetData>{row_xml}</sheetData></worksheet>'
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("xl/sharedStrings.xml", sst_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)


class TestXlsx:
    def test_basic_extraction(self, tmp_path):
        p = tmp_path / "data.xlsx"
        _make_xlsx(p, [
            ["성명", "주민번호", "연락처"],
            ["홍길동", "880101-1234568", "010-1234-5678"],
            ["김민수", "950101-2345676", "010-9999-8888"],
        ])
        text = read_text(str(p))
        assert "홍길동" in text
        assert "880101-1234568" in text

    def test_records_mode(self, tmp_path):
        p = tmp_path / "data.xlsx"
        _make_xlsx(p, [
            ["성명", "주민번호"],
            ["홍길동", "880101-1234568"],
        ])
        records = read_records(str(p))
        assert len(records) == 1
        assert records[0]["성명"] == "홍길동"


# ─────────────────────────────────────────────────────────────────────
# 통합: read_text + Anonymizer
# ─────────────────────────────────────────────────────────────────────

class TestE2EAnonymization:
    def test_hwpx_to_anonymizer(self, tmp_path):
        """파일 → 텍스트 → Anonymizer 의 end-to-end 흐름."""
        from ko_pii import Anonymizer, ProcessingMode

        p = tmp_path / "doc.hwpx"
        _make_hwpx(p, [
            "신청인 홍길동",
            "주민번호 880101-1234568",
            "연락처 010-1234-5678",
        ])
        text = read_text(str(p))
        result = Anonymizer(mode=ProcessingMode.STRICT).process(text)
        assert "880101-1234568" not in result.text
        assert "010-1234-5678" not in result.text
        # 결합 위험도 CRITICAL (식별자 RRN 등장)
        from ko_pii.core.types import RiskLevel
        assert result.combined_risk.combined_risk == RiskLevel.CRITICAL
