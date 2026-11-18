"""Explicit birth-date headers must not become silently unmapped table cells."""
import unicodedata

import pytest

from ko_pii import ProcessingMode, ReversibleVault
from ko_pii.io_ import read_records
from ko_pii.tabular import anonymize_records, anonymize_value, classify_schema_columns, map_columns


HEADERS = ["생년월일", "출생일", "출생일자", "생일", "DOB", "dob", "Date of Birth",
           "date_of_birth", "Birth Date", "birth_date", "birthdate", "생년월일(양력)", "생년월일(음력)"]


@pytest.mark.parametrize("header", HEADERS)
def test_exact_birth_headers_are_classified_with_declared_evidence(header):
    assert map_columns([header]) == {header: "DT_BIRTH"}
    classified = classify_schema_columns([header])[header]
    assert classified.label == "DT_BIRTH" and classified.confidence == 1.0
    assert classified.match == "exact" and not classified.ambiguous


@pytest.mark.parametrize("header", HEADERS)
@pytest.mark.parametrize("mode", list(ProcessingMode))
def test_auto_mapped_birth_dates_follow_asserted_column_modes_and_vault_contract(header, mode):
    records = [{header: "1988-01-01", "비고": "public"}, {header: "1988-01-01", "비고": "public"}]
    vault = ReversibleVault(salt="birth-column", secret_key="test", fingerprint_iterations=1)
    output, actual_vault = anonymize_records(records, mode=mode, vault=vault)
    assert actual_vault is vault and records[0][header] == "1988-01-01"
    if mode == ProcessingMode.AUDIT:
        assert output == records and not vault.entries()
    else:
        assert output == [{header: "<DT_BIRTH_1>", "비고": "public"}] * 2
        assert vault.reveal("<DT_BIRTH_1>") == "1988-01-01"


@pytest.mark.parametrize("header", ["접수일자", "작성일자", "date", "생년월일 메모", "예상생일", "product_birth_date", "birth_date_notes", "생년월일(이메일)"])
def test_unknown_mixed_and_ordinary_date_headers_are_not_inferred_as_birth_columns(header):
    assert map_columns([header]) == {}
    records = [{header: "1988-01-01"}]
    assert anonymize_records(records, strategy="redact")[0] == records


@pytest.mark.parametrize("header", ["생년월일", "신청인 생년월일", "전화번호", "고객 전화번호"])
def test_canonical_hangul_header_normalization_preserves_the_original_key(header):
    raw = unicodedata.normalize("NFD", header)
    label = "DT_BIRTH" if "생년월일" in header else "PHONE"
    value = "1988-01-01" if label == "DT_BIRTH" else "010-1234-5678"
    assert map_columns([raw]) == {raw: label}
    output, vault = anonymize_records([{raw: value}])
    assert output == [{raw: "<" + label + "_1>"}]
    assert vault.reveal("<" + label + "_1>") == value


@pytest.mark.parametrize("header", ["ｅｍａｉｌ", "e\u200bmail", "ｃｕｓｔｏｍｅｒ＿ｅｍａｉｌ", "customer_e\u200bmail"])
def test_compatibility_and_invisible_characters_are_normalized_only_for_lookup(header):
    assert map_columns([header]) == {header: "EMAIL"}
    output, _ = anonymize_records([{header: "demo@example.com"}], strategy="redact")
    assert output == [{header: "[이메일]"}]


@pytest.mark.parametrize("header", ["product_ｅｍａｉｌ", "ｅｍａｉｌ＿ｎｏｔｅｓ", "ｅｍａｉｌ(비고)"])
def test_header_normalization_does_not_enable_substring_or_arbitrary_annotation_inference(header):
    assert map_columns([header]) == {}


def test_normalized_exact_header_has_normalized_not_exact_classification():
    header = unicodedata.normalize("NFD", "생년월일")
    result = classify_schema_columns([header])[header]
    assert result.match == "normalized" and result.confidence == 0.95


def test_explicit_empty_mapping_still_disables_automatic_birth_mapping():
    records = [{"생년월일": "1988-01-01"}]
    assert anonymize_records(records, column_map={})[0] == records


@pytest.mark.parametrize("value", [True, 1988.0101])
def test_newly_mapped_invalid_cells_fail_before_other_cells_mutate_the_vault(value):
    vault = ReversibleVault(salt="birth-column", secret_key="test", fingerprint_iterations=1)
    with pytest.raises(ValueError, match="mapped cells"):
        anonymize_records([{"성명": "John Smith", "生年": "public", "생년월일": value}], vault=vault)
    assert not vault.entries()


@pytest.mark.parametrize("strategy", ["tokenize", "redact", "asterisk", "partial", "hashed", "fpe"])
@pytest.mark.parametrize("value", ["1988-01-01", 19880101])
def test_birth_column_strategies_use_the_existing_explicit_value_contract(strategy, value):
    vault = ReversibleVault(salt="birth-strategy", secret_key="test", fingerprint_iterations=1)
    expected, _ = anonymize_value(str(value), "DT_BIRTH", strategy=strategy, vault=vault)
    records = [{"생년월일": value, "count": 7}]
    output, _ = anonymize_records(records, strategy=strategy, vault=vault)
    assert output == [{"생년월일": expected, "count": 7}]
    assert str(value) not in expected
    assert records == [{"생년월일": value, "count": 7}]


def test_null_empty_birth_cells_and_distinct_normalized_header_keys_are_preserved():
    records = [{"생년월일": "", "DOB": None}, {"ｅｍａｉｌ": "first@example.com", "email": "second@example.com"}]
    output, vault = anonymize_records(records)
    assert output == [{"생년월일": "", "DOB": None}, {"ｅｍａｉｌ": "<EMAIL_1>", "email": "<EMAIL_2>"}]
    assert vault.reveal("<EMAIL_1>") == "first@example.com"
    assert vault.reveal("<EMAIL_2>") == "second@example.com"


def test_csv_ingestion_keeps_raw_headers_and_masks_the_complete_birth_cell(tmp_path):
    name_header = unicodedata.normalize("NFD", "성명")
    birth_header = unicodedata.normalize("NFD", "생년월일")
    source = tmp_path / "applicants.csv"
    source.write_text(name_header + "," + birth_header + ",비고\nJohn Smith,1988-01-01,public\n", encoding="utf-8")
    records = read_records(str(source))
    output, vault = anonymize_records(records)
    assert output == [{name_header: "<PERSON_1>", birth_header: "<DT_BIRTH_1>", "비고": "public"}]
    assert vault.reveal("<PERSON_1>") == "John Smith"
    assert vault.reveal("<DT_BIRTH_1>") == "1988-01-01"
