"""Literal person fields protect long and non-Hangul values without general NER."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json, detect_all


NAMES = ["레오나르도다빈치", "장피에르뒤퐁", "김마리아은", "김 민수", "남궁 다은", "John Smith",
         "Anne-Marie O'Neill", "J. R. Tolkien", "José Álvarez", "金民秀", "洪吉童", "林", "A"]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("label", ["성명", "성함", "성명(영문)", "성명(한자)"])
def test_explicit_person_field_protects_the_complete_literal_name(name, label):
    source = label + ": " + name
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == label + ": [성명]"
    assert [(item.detection.start, item.detection.end, item.detection.text) for item in result.detections] == [
        (len(label) + 2, len(source), name),
    ]
    assert "pattern:person_literal_name_field" in result.detections[0].detection.evidence


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_repeated_exact_values_before_and_after_the_field_share_a_vault_token(name, form):
    raw = unicodedata.normalize(form, name)
    prefix = unicodedata.normalize(form, "성명: ")
    source = raw + "\n" + prefix + raw + "\n(" + raw + ")"
    vault = ReversibleVault(salt="extended-fields", secret_key="test", fingerprint_iterations=1)
    engine = Anonymizer(vault=vault, include=["PERSON"])
    result = engine.process(source)
    assert result.text == "<PERSON_1>\n" + prefix + "<PERSON_1>\n(<PERSON_1>)"
    assert vault.reveal("<PERSON_1>") == raw
    assert len(result.detections) == 3
    assert all(source[item.detection.start:item.detection.end] == raw for item in result.detections)


@pytest.mark.parametrize("alternative", ["金民秀", "Kim Min-su"])
def test_parenthetical_name_forms_are_separate_values_and_not_left_in_cleartext(alternative):
    source = "성명: 김민수 (" + alternative + ")\n" + alternative
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == "성명: [성명] ([성명])\n[성명]"


@pytest.mark.parametrize("source,expected", [
    ("성명: John Smith, 김다은", "성명: [성명], [성명]"),
    ("성명: 김다은 / John Smith / 金民秀", "성명: [성명] / [성명] / [성명]"),
    ("성명: N/A, John Smith, None, 박보라", "성명: N/A, [성명], None, [성명]"),
    ("성명: 아나스타샤김입니다.", "성명: [성명]입니다."),
    ("성명: 홍길동에게, John Smith", "성명: [성명]에게, [성명]"),
    ("성명: John Smith 연락처: 010-1234-5678", "성명: [성명] 연락처: 010-1234-5678"),
])
def test_mixed_lists_and_following_metadata_keep_their_boundaries(source, expected):
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == expected


@pytest.mark.parametrize("source", [
    "파일성명: John Smith", "고객성명: John Smith", "é성명: John Smith", "金성명: John Smith",
    "성명서: John Smith", "이름: John Smith", "주소: John Smith", "John Smith",
    "성명: 해당 없음", "성명: N/A", "성명: John123", "성명: John_Smith",
    "성명: 홍길동이 신청서를 제출했다.",
])
def test_ordinary_prose_other_fields_and_malformed_identifiers_do_not_gain_extended_evidence(source):
    assert all("pattern:person_literal_name_field" not in item.evidence
               for item in detect_all(source, include=["PERSON"]))


def test_alias_reuse_requires_a_complete_word_and_does_not_fuse_new_records():
    source = "성명: John Smith\nXJohn Smith\nJohn SmithX\nJohn_Smith\nJohn\nSmith"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == (
        "성명: [성명]\nXJohn Smith\nJohn SmithX\nJohn_Smith\nJohn\nSmith"
    )


def test_confirmed_long_name_with_a_korean_particle_and_copula_keeps_the_suffix():
    source = "레오나르도다빈치에게 전달.\n성명: 레오나르도다빈치\n레오나르도다빈치입니다."
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == "[성명]에게 전달.\n성명: [성명]\n[성명]입니다."


def test_exclusions_audit_and_document_isolation_still_apply():
    source = "성명: John Smith / 金民秀"
    engine = Anonymizer(strategy="redact", include=["PERSON"], person_exclusions=["John Smith"])
    assert engine.process(source).text == "성명: John Smith / [성명]"
    assert engine.process("金民秀").text == "金民秀"
    audit = Anonymizer(mode=ProcessingMode.AUDIT).process(source)
    assert audit.text == source and not audit.substitutions


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_exact_exclusions_cover_direct_and_reused_extended_names(name, form):
    raw = unicodedata.normalize(form, name)
    source = "성명: " + raw + "\n" + raw
    engine = Anonymizer(strategy="redact", include=["PERSON"], person_exclusions=[raw])
    assert engine.process(source).text == source
    assert not engine.vault.entries()


def test_a_whole_compound_name_exclusion_is_not_a_global_component_whitelist():
    source = "성명: 남궁 다은\n남궁 다은\n성명: 남궁\n남궁"
    engine = Anonymizer(strategy="redact", include=["PERSON"], person_exclusions=["남궁 다은"])
    assert engine.process(source).text == "성명: 남궁 다은\n남궁 다은\n성명: [성명]\n[성명]"


def test_structured_note_uses_the_same_literal_field_logic():
    result = anonymize_json({"note": "성명(한자): 金民秀"},
                            anonymizer=Anonymizer(strategy="redact", include=["PERSON"]))
    assert result.data == {"note": "성명(한자): [성명]"}


def test_origin_metadata_never_exempts_a_confirmed_name_from_masking():
    source = "성명: 장피에르뒤퐁 / John Smith / 金民秀 / 짐캐리"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == (
        "성명: [성명] / [성명] / [성명] / [성명]"
    )


@pytest.mark.parametrize("gap", ["\n", "\t", " | ", "; "])
def test_extended_field_context_stops_at_a_new_record_or_cell(gap):
    source = "성명: John Smith" + gap + "李太成"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == "성명: [성명]" + gap + "李太成"


@pytest.mark.parametrize("name", ["John Smith", "金民秀", "장피에르뒤퐁", "José Álvarez"])
@pytest.mark.parametrize("strategy", ["tokenize", "redact", "asterisk", "hashed", "fpe"])
def test_full_replacement_strategies_do_not_return_the_literal_name(name, strategy):
    vault = ReversibleVault(salt="strategies", secret_key="test", fingerprint_iterations=1)
    source = "성명: " + name
    result = Anonymizer(strategy=strategy, include=["PERSON"], vault=vault).process(source)
    assert result.text.startswith("성명: ")
    assert name not in result.text and len(result.substitutions) == 1


def test_overlapping_confirmed_multiword_names_do_not_leave_an_unprotected_remainder():
    source = "성명: Ann Lee\n성명: Lee Park\nAnn Lee Park"
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert "Ann" not in result.text and "Lee" not in result.text and "Park" not in result.text


@pytest.mark.parametrize("size", [128, 129])
def test_field_length_bound_does_not_silently_claim_a_truncated_prefix(size):
    source = "성명: " + "Z" * size
    found = detect_all(source, include=["PERSON"])
    if size == 128:
        assert [(item.start, item.end) for item in found] == [(4, len(source))]
    else:
        assert found == []


def test_explicit_structured_field_assertion_handles_values_outside_literal_grammar():
    source = {"client": "Client_123 " + "Z" * 129}
    result = anonymize_json(source, field_labels={"/client": "PERSON"},
                            anonymizer=Anonymizer(strategy="redact", include=["PERSON"]))
    assert result.data == {"client": "[성명]"}


@pytest.mark.parametrize("wrapper", [('"', '"'), ("__", "__"), ("**", "**"), ("`", "`")])
def test_wrapped_field_values_preserve_padding_but_not_the_name(wrapper):
    source = "성명: " + wrapper[0] + "  John Smith  " + wrapper[1]
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == "성명: " + wrapper[0] + "  [성명]  " + wrapper[1]


@pytest.mark.parametrize("wrapper", ['"', "__", "**", "`"])
def test_an_unclosed_empty_value_does_not_start_a_name_list(wrapper):
    source = "성명: " + wrapper + "N/A, John Smith"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == source


def test_decomposed_hangul_prose_is_not_reinterpreted_as_a_multilingual_name():
    source = "성명: " + unicodedata.normalize("NFD", "홍길동이 신청서를 제출했다") + "."
    assert all("pattern:person_literal_name_field" not in item.evidence
               for item in detect_all(source, include=["PERSON"], normalize=False))


@pytest.mark.parametrize("name", ["John Smith", "김다은"])
@pytest.mark.parametrize("normalize", [True, False])
def test_combining_mark_does_not_split_a_larger_word_into_a_person_label(name, normalize):
    source = "x\u0301성명: " + name
    assert all(not any(part.startswith("pos:field_label(") for part in item.evidence)
               for item in detect_all(source, include=["PERSON"], normalize=normalize))
