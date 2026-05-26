from ko_pii.tabular import anonymize_records, map_columns
from ko_pii.core.modes import ProcessingMode


class TestColumnMapping:
    def test_basic_mapping(self):
        m = map_columns(["성명", "주민번호", "연락처"])
        assert m["성명"] == "PERSON"
        assert m["주민번호"] == "RRN"
        assert m["연락처"] == "PHONE"

    def test_english_headers(self):
        m = map_columns(["name", "phone", "email"])
        assert m["name"] == "PERSON"
        assert m["phone"] == "PHONE"
        assert m["email"] == "EMAIL"

    def test_composite_header(self):
        m = map_columns(["신청인 성명", "고객 연락처"])
        assert m["신청인 성명"] == "PERSON"
        assert m["고객 연락처"] == "PHONE"

    def test_unmapped_passthrough(self):
        m = map_columns(["메모", "비고", "기타사항"])
        assert m == {}


class TestAnonymizeRecords:
    def test_basic_anonymization(self):
        records = [
            {"성명": "홍길동", "주민번호": "880101-1234568", "비고": "신청"},
            {"성명": "김민수", "주민번호": "950101-2345676", "비고": "보호자"},
        ]
        out, vault = anonymize_records(records, mode=ProcessingMode.STRICT, strategy="tokenize")
        assert len(out) == 2
        # 매핑된 컬럼은 가명화
        assert out[0]["성명"] != "홍길동"
        assert out[0]["주민번호"] != "880101-1234568"
        # 매핑되지 않은 컬럼은 그대로
        assert out[0]["비고"] == "신청"
        # vault 에서 복원 가능
        token = out[0]["성명"]
        assert vault.reveal(token) == "홍길동"

    def test_same_value_same_token(self):
        records = [
            {"성명": "홍길동", "주민번호": "880101-1234568"},
            {"성명": "홍길동", "주민번호": "880101-1234568"},
        ]
        out, _ = anonymize_records(records, strategy="tokenize")
        assert out[0]["성명"] == out[1]["성명"]
        assert out[0]["주민번호"] == out[1]["주민번호"]

    def test_explicit_column_map(self):
        records = [{"col1": "880101-1234568", "col2": "010-1234-5678"}]
        out, _ = anonymize_records(
            records,
            column_map={"col1": "RRN", "col2": "PHONE"},
            strategy="redact",
        )
        assert out[0]["col1"] == "[주민등록번호]"
        assert out[0]["col2"] == "[전화번호]"

    def test_partial_strategy(self):
        records = [{"성명": "홍길동", "전화번호": "010-1234-5678"}]
        out, _ = anonymize_records(records, strategy="partial")
        assert out[0]["성명"] == "홍OO"
        assert out[0]["전화번호"] == "010-****-5678"

    def test_empty_records(self):
        out, vault = anonymize_records([])
        assert out == []

    def test_empty_value_preserved(self):
        records = [{"성명": "", "주민번호": "880101-1234568"}]
        out, _ = anonymize_records(records)
        assert out[0]["성명"] == ""
