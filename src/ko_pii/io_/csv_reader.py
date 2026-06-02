"""CSV / TSV 텍스트 추출 — 헤더 인식 + 레코드 반환."""
from __future__ import annotations

import csv
import io

from ko_pii.io_.plain import read_text as _plain_read


def read_text(path: str) -> str:
    """전체 내용을 평문으로 반환 (헤더 포함)."""
    return _plain_read(path)


def read_records(path: str) -> list[dict[str, str]]:
    """첫 행을 헤더로 인식, 이후를 dict 리스트로 반환."""
    raw = _plain_read(path)
    if not raw.strip():
        return []
    # Sniff delimiter
    try:
        dialect = csv.Sniffer().sniff(raw[:8192], delimiters=",\t;|")
    except csv.Error:
        # Fallback to comma or tab heuristic
        dialect = csv.excel_tab if "\t" in raw[:1024] else csv.excel
    # io.StringIO 로 넘겨야 csv 파서가 따옴표 안의 줄바꿈(멀티라인 셀)을 보존한다.
    # raw.splitlines() 는 따옴표 내부 줄바꿈에서 끊어 셀을 깨뜨림.
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    return [dict(row) for row in reader if any(row.values())]
