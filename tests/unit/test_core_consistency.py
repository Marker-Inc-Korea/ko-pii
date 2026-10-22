"""Core regressions: normalization, field context and tabular contracts."""
from copy import deepcopy

import pytest

from ko_pii import Anonymizer, ProcessingMode, detect_all
from ko_pii.core.unicode_norm import needs_normalization, normalize_unicode
from ko_pii.patterns import rrn
from ko_pii.tabular import anonymize_records, classify_schema_columns, map_columns
from ko_pii.vault.reversible import ReversibleVault


@pytest.mark.parametrize("prefix", ["", "Phone: ", "연락처: "])
@pytest.mark.parametrize("sample", ["010-12O4-5678", "O10-1234-5678", "010-1234-567B"])
def test_homoglyph_policy_is_independent_of_surrounding_language(prefix, sample):
    text = prefix + sample + "!"
    assert needs_normalization(text)
    matches = detect_all(text, include=["PHONE"])
    assert len(matches) == 1
    match = matches[0]
    assert (match.start, match.end, match.text) == (len(prefix), len(prefix) + len(sample), sample)
    assert Anonymizer(strategy="redact", include=["PHONE"]).process(text).text == prefix + "[전화번호]!"


@pytest.mark.parametrize("text", [
    "NO SOS ID", "model12O4", "file_12O4", "12O4value", "010-1234-5678",
    "ref010-12O4-5678", "010-12O4-5678code", "MODEL-010-12O4-5678",
])
def test_normalization_does_not_fold_identifier_fragments_or_plain_digits(text):
    assert not needs_normalization(text)
    assert normalize_unicode(text)[0] == text
    # The Hangul fast path must use the same token boundaries.
    assert normalize_unicode("제품 " + text)[0] == "제품 " + text


@pytest.mark.parametrize("field", ["주민번호 ", "주민등록번호: ", "주민 등록 번호 = ", "RRN: "])
def test_rrn_field_preserves_reduced_confidence_without_hyphen(field):
    for number in ("8801011234567", "880101-1234567"):
        text = field + number
        matches = list(rrn.detect(text))
        assert len(matches) == 1
        assert matches[0].confidence == 0.7
        assert "context:rrn_field" in matches[0].evidence
        assert text[matches[0].start:matches[0].end] == number


@pytest.mark.parametrize("text", [
    "8801011234567", "바코드 8801011234567", "바코드번호 8801234567890",
    "8801043001212 (농심 신라면)", "주민번호를 입력하고 바코드 8801011234567",
    "주민번호: 미기재\n바코드: 8801011234567", "주민번호:\n8801011234567",
    "주민번호: 8802311234567", "주민번호: 8801015234567",
    "주민번호: 188010112345671",
])
def test_rrn_field_exception_is_local_and_keeps_format_checks(text):
    assert not list(rrn.detect(text))


@pytest.mark.parametrize("strategy", ["tokenize", "redact", "asterisk", "partial", "hashed", "fpe"])
@pytest.mark.parametrize("explicit", [False, True])
def test_table_audit_preserves_cells_and_supplied_vault(strategy, explicit):
    records = [{"연락처": "010-1234-5678", "성명": "홍길동", "메모": "내용", "empty": "",
                None: ["010-1234-5678", "", None]}, {"성명": "김민수"}]
    original = deepcopy(records)
    vault = ReversibleVault()
    vault.store("PHONE", "010-1234-5678", 4, offset=7)
    before = deepcopy(vault.to_dict())
    out, returned = anonymize_records(
        records, mode=ProcessingMode.AUDIT, strategy=strategy, vault=vault,
        column_map={"연락처": "PHONE", "성명": "PERSON"} if explicit else None,
    )
    assert out == records == original
    assert out is not records and out[0] is not records[0]
    assert out[0][None] is not records[0][None]
    assert returned is vault and vault.to_dict() == before


def test_table_audit_without_existing_vault_and_invalid_strategy():
    records = [{"연락처": "010-1234-5678"}]
    out, vault = anonymize_records(records, mode=ProcessingMode.AUDIT)
    assert out == records and len(vault) == 0
    with pytest.raises(ValueError, match="Unknown strategy"):
        anonymize_records(records, mode=ProcessingMode.AUDIT, strategy="typo")


@pytest.mark.parametrize("header", [
    "상품이름", "filename", "product_name", "사용자이름설명", "고객 연락처 메모", "성명/연락처",
    "신청인 성명/연락처", "주소변경이력", "상품 이름",
])
def test_conservative_headers_do_not_force_unrelated_cells(header):
    assert map_columns([header]) == {}
    records = [{header: "report.txt"}]
    assert anonymize_records(records)[0] == records


@pytest.mark.parametrize(("header", "label"), [
    ("신청인 연락처", "PHONE"), ("신청인 성명", "PERSON"), ("고객연락처", "PHONE"),
    ("customer_phone", "PHONE"), ("USER-NAME", "PERSON"), ("성 명", "PERSON"),
    ("EMAIL", "EMAIL"), ("신청인 주민등록번호", "RRN"),
])
def test_conservative_headers_use_complete_qualified_field(header, label):
    assert map_columns(iter([header])) == {header: label}


def test_schema_classification_stays_exact_only():
    assert classify_schema_columns(["신청인 연락처", "customer_phone"]) == {}


def test_legacy_mapping_is_opt_in_and_explicit_mapping_wins():
    headers = ["상품이름", "filename", "신청인 연락처"]
    assert map_columns(headers, header_policy="legacy") == dict.fromkeys(headers, "PERSON")
    records = [{"filename": "report.txt", "신청인 연락처": "010-1234-5678"}]
    assert anonymize_records(records, header_policy="legacy", strategy="redact")[0] == [
        dict.fromkeys(records[0], "[성명]")
    ]
    for policy in ("conservative", "legacy"):
        assert anonymize_records(records, column_map={}, header_policy=policy)[0] == records
        out, _ = anonymize_records(
            records, column_map={"신청인 연락처": "PHONE"}, header_policy=policy, strategy="redact",
        )
        assert out == [{"filename": "report.txt", "신청인 연락처": "[전화번호]"}]


def test_header_policy_rejects_typos_even_with_empty_input():
    with pytest.raises(ValueError, match="header_policy"):
        map_columns([], header_policy="typo")
    with pytest.raises(ValueError, match="header_policy"):
        anonymize_records([], header_policy="typo")
