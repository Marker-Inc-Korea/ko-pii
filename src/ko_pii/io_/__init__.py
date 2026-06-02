"""파일 입력 (Document I/O) — 한국 공공 부문 문서 포맷 텍스트 추출.

지원 포맷 (모두 표준 라이브러리만 사용):
- ``.txt``, ``.md`` — plain text (UTF-8 / cp949 자동 감지)
- ``.hwpx``        — HWPX (한컴 OWPML, KS X 6101)
- ``.docx``        — Microsoft Word OOXML
- ``.xlsx``        — Microsoft Excel OOXML (텍스트 셀)
- ``.csv``, ``.tsv`` — 표 형식 (헤더 + 행 단위)

PDF (pdfplumber/pypdf) 와 HWP 5.x (olefile) 도 ``pip install ko-pii[file]`` 설치 시
dispatcher 가 자동 라우팅해 지원한다.

사용:
    from ko_pii.io_ import read_text
    text = read_text("input.hwpx")
"""
from ko_pii.io_.dispatcher import read_text, read_records, SUPPORTED_EXTENSIONS

__all__ = ["read_text", "read_records", "SUPPORTED_EXTENSIONS"]
