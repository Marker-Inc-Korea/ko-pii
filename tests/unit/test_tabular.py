import pytest

from ko_pii.tabular import (
    anonymize_records,
    anonymize_value,
    classify_schema_columns,
    map_columns,
)
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


class TestSchemaColumnClassification:
    def test_exact_sensitive_columns_include_evidence(self):
        classified = classify_schema_columns(["성명", "주민등록번호"])

        assert classified["성명"].label == "PERSON"
        assert classified["성명"].confidence == 1.0
        assert classified["성명"].ambiguous is False
        assert classified["주민등록번호"].label == "RRN"

    def test_normalized_match_is_explicit(self):
        classified = classify_schema_columns(["성 명"])

        assert classified["성 명"].match == "normalized"
        assert classified["성 명"].confidence == 0.95

    def test_generic_name_requires_review(self):
        classified = classify_schema_columns(["name"])

        assert classified["name"].label == "PERSON"
        assert classified["name"].ambiguous is True
        assert classified["name"].confidence == 0.60

    @pytest.mark.parametrize("column", ["product_name", "사용자이름설명", "고객 연락처 메모"])
    def test_schema_classification_never_uses_substrings(self, column):
        assert classify_schema_columns([column]) == {}


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

    def test_explicit_value_anonymization(self):
        output, _ = anonymize_value("홍길동", "PERSON", strategy="redact")

        assert output == "[성명]"

    def test_explicit_value_rejects_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            anonymize_value("홍길동", "PERSON", strategy="unknown")
