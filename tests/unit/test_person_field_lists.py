"""Literal name lists retain item boundaries and do not escape their field."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json, detect_all


NAMES = ["김다은", "박보라", "남궁다은"]


@pytest.mark.parametrize("separator", [", ", " / ", " & ", "·", "-", "\t,\t"])
@pytest.mark.parametrize("wrapper", [("", ""), ('"', '"'), ("“", "”"), ("**", "**"), ("`", "`")])
def test_every_item_in_one_explicit_name_field_is_fully_replaced(separator, wrapper):
    values = [wrapper[0] + name + wrapper[1] for name in NAMES]
    source = "참석자: " + separator.join(values)
    expected = "참석자: " + separator.join(wrapper[0] + "[성명]" + wrapper[1] for _ in NAMES)
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == expected
    detections = [item.detection for item in result.detections]
    assert [item.text for item in detections] == NAMES
    assert all(source[item.start:item.end] == item.text for item in detections)
    assert all("pattern:person_name_field_list" in item.evidence for item in detections[1:])
    assert "pattern:person_name_field_list" not in detections[0].evidence


@pytest.mark.parametrize("prefix,suffix", [
    ("[성명] ", ""), ("【성명】 ", ""), ("**성명**: ", ""),
    ("__성명__ = __", "__"), ("`성명`: `", "`"),
    ("| 성명 | ", " | public |"), ("[성 명(한글)]: ", ""),
])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_framed_labels_preserve_raw_offsets_and_vault_values(prefix, suffix, form):
    prefix = unicodedata.normalize(form, "\ufb03 " + prefix)
    raw = unicodedata.normalize(form, "김다은")
    source = prefix + raw + suffix
    vault = ReversibleVault(salt="field-list", secret_key="test", fingerprint_iterations=1)
    result = Anonymizer(include=["PERSON"], vault=vault).process(source)
    assert result.text == prefix + "<PERSON_1>" + suffix
    item = result.detections[0].detection
    assert (item.start, item.end, item.text) == (len(prefix), len(prefix) + len(raw), raw)
    assert vault.reveal("<PERSON_1>") == raw


@pytest.mark.parametrize("skipped", ["없음", "비공개", "해당없음", "미입력정보없음", "별도제외"])
def test_non_name_or_excluded_item_does_not_hide_the_following_name(skipped):
    source = "성명: 김다은, " + skipped + ", 박보라"
    result = Anonymizer(include=["PERSON"], strategy="redact", person_exclusions=["별도제외"]).process(source)
    assert result.text.endswith(", [성명]")
    if skipped != "미입력정보없음":
        assert skipped in result.text


@pytest.mark.parametrize("gap", ["\n", "\r\n", "\u2028", " | ", "; ", ", 메모: ", " 및 "])
def test_list_context_does_not_cross_records_cells_or_arbitrary_prose(gap):
    source = "성명: 김다은" + gap + "박보라"
    found = detect_all(source, include=["PERSON"])
    second = [item for item in found if item.start >= source.index("박보라")]
    assert all("pattern:person_name_field" not in item.evidence for item in second)
    assert all("pattern:person_name_field_list" not in item.evidence for item in second)


@pytest.mark.parametrize("source", [
    "이름: 인삼, 당귀", "주소: 김다은, 박보라", "[파일이름]: 김다은, 박보라",
    "**성명서**: 김다은, 박보라", "【대리인수】 김다은, 박보라",
])
def test_lists_without_a_person_field_do_not_gain_literal_name_evidence(source):
    assert all("pattern:person_name_field" not in item.evidence
               for item in detect_all(source, include=["PERSON"]))


def test_exclusions_audit_and_per_document_reuse_stay_scoped():
    source = "박보라.\n성명: 김다은, 박보라\n박보라에게 전달"
    engine = Anonymizer(include=["PERSON"], strategy="redact", person_exclusions=["김다은"])
    assert engine.process(source).text == "[성명].\n성명: 김다은, [성명]\n[성명]에게 전달"
    assert engine.process("박보라").text == "박보라"
    audit = Anonymizer(mode=ProcessingMode.AUDIT, include=["PERSON"]).process(source)
    assert audit.text == source and not audit.substitutions


def test_structured_note_accepts_list_syntax_without_a_custom_schema():
    result = anonymize_json({"note": "[성명] 김다은, 박보라", "public": "ok"},
                            anonymizer=Anonymizer(include=["PERSON"], strategy="redact"))
    assert result.data == {"note": "[성명] [성명], [성명]", "public": "ok"}


@pytest.mark.parametrize("name", ["가동", "지하", "지상", "호실"])
def test_address_unit_words_can_still_be_confirmed_as_names_in_explicit_fields(name):
    source = "성명: " + name + "\n" + name + "에게 전달"
    assert Anonymizer(include=["PERSON"], strategy="redact").process(source).text == (
        "성명: [성명]\n[성명]에게 전달"
    )


@pytest.mark.parametrize("detail", ["지하 1층", "지상2층", "가동101호", "101호실에서"])
def test_typed_address_units_do_not_turn_into_people_near_a_phone(detail):
    source = detail + "; 연락처: 010-1234-5678"
    assert detect_all(source, include=["PERSON"]) == []


@pytest.mark.parametrize("empty", ["N/A", "n/a", "N.A.", "NA", "NULL", "None"])
@pytest.mark.parametrize("prefix", ["성명: ", "[성명] ", "| 성명 | "])
@pytest.mark.parametrize("wrapper", [("", ""), ('"', '"'), ("**", "**"), ("__", "__"), ("`", "`")])
def test_ascii_empty_items_preserve_only_the_current_literal_name_list_context(prefix, empty, wrapper):
    empty = wrapper[0] + empty + wrapper[1]
    source = prefix + empty + ", 김다은, " + empty + ", 박보라"
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == prefix + empty + ", [성명], " + empty + ", [성명]"


@pytest.mark.parametrize("source", [
    "성명: N/A\n박보라", "성명: N/A | 박보라", "성명: N/A; 박보라",
    "성명: nullable, 박보라", "성명: null_value, 박보라", "성명: noneworthy, 박보라",
    "주소: N/A, 박보라", "성명: example.com/NA, 박보라", "성명: __None__value, 박보라",
])
def test_empty_markers_do_not_match_word_fragments_urls_or_other_records(source):
    assert all("pattern:person_name_field_list" not in item.evidence
               for item in detect_all(source, include=["PERSON"]))


def test_ascii_empty_items_keep_audit_exclusions_and_per_document_isolation():
    source = "성명: N/A, 김다은, NULL, 박보라"
    engine = Anonymizer(include=["PERSON"], strategy="redact", person_exclusions=["김다은"])
    assert engine.process(source).text == "성명: N/A, 김다은, NULL, [성명]"
    assert engine.process("박보라").text == "박보라"
    assert Anonymizer(mode=ProcessingMode.AUDIT).process(source).text == source
