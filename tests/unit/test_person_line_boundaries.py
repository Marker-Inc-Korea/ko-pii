"""Names in separate records must survive the numeric anti-evasion view."""
import json
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json, detect_all
from ko_pii.patterns.person import detect


LINE_BREAKS = ["\n", "\r", "\r\n", "\v", "\f", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029", "\n\n", "\r\n \t\r\n"]


@pytest.mark.parametrize("line", LINE_BREAKS)
@pytest.mark.parametrize("form", ["NFC", "NFD"])
@pytest.mark.parametrize("name", ["김다은", "김빛나라", "김태성"])
def test_person_fields_on_both_sides_of_a_line_break_keep_full_source_spans(line, form, name):
    prefix = "성명:" + line
    raw = unicodedata.normalize(form, name)
    source = prefix + raw + line + "주소: 서울"
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + "[성명]" + line + "주소: 서울"
    assert [(r.detection.start, r.detection.end, r.detection.text) for r in result.detections] == [
        (len(prefix), len(prefix) + len(raw), raw),
    ]


@pytest.mark.parametrize("line", LINE_BREAKS)
def test_low_level_detector_and_normalization_opt_out_understand_line_boundaries(line):
    source = "성명:" + line + "김다은" + line + "주소: 서울"
    assert [d.text for d in detect(source)] == ["김다은"]
    assert [d.text for d in detect_all(source, include=["PERSON"], normalize=False)] == ["김다은"]


@pytest.mark.parametrize("line", LINE_BREAKS)
def test_line_aware_names_reuse_tokens_without_swallowing_the_record_separator(line):
    source = "성명: 김다은" + line + "성명: 김다은"
    engine = Anonymizer(include=["PERSON"])
    result = engine.process(source)
    assert result.text == "성명: <PERSON_1>" + line + "성명: <PERSON_1>"
    restored = ReversibleVault.from_dict(json.loads(json.dumps(engine.vault.to_dict())))
    assert restored.reveal("<PERSON_1>") == "김다은"


@pytest.mark.parametrize("line", LINE_BREAKS)
def test_exclusions_and_audit_are_applied_to_every_person_text_view(line):
    source = "성명: 김다은" + line + "주소: 서울"
    engine = Anonymizer(include=["PERSON"], person_exclusions=["김다은"])
    assert engine.process(source).text == source
    assert not engine.vault.entries()
    audit = Anonymizer(include=["PERSON"], mode=ProcessingMode.AUDIT)
    result = audit.process(source)
    assert result.text == source and not result.substitutions and not audit.vault.entries()


@pytest.mark.parametrize("line", ["\v", "\f", "\x85", "\u2028", "\u2029"])
def test_structured_free_text_uses_the_same_person_boundaries(line):
    source = {"note": "성명: 김다은" + line + "주소: 서울", "safe": "public"}
    result = anonymize_json(source, anonymizer=Anonymizer(strategy="redact", include=["PERSON"]))
    assert result.data == {"note": "성명: [성명]" + line + "주소: 서울", "safe": "public"}


@pytest.mark.parametrize("quotes", [("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』")])
@pytest.mark.parametrize("name", ["김다은", "김빛나라"])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_quoted_names_are_masked_without_removing_typographic_quotes(quotes, name, form):
    left, right = quotes
    prefix = "성명:\n\n" + left
    source = prefix + unicodedata.normalize(form, name) + right + "\n주소: 서울"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == prefix + "[성명]" + right + "\n주소: 서울"


@pytest.mark.parametrize("control", ["\v", "\f", "\x85"])
def test_existing_control_injection_protection_inside_a_name_is_not_removed(control):
    source = "성명: 김다" + control + "은"
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(source).text == "성명: [성명]"


@pytest.mark.parametrize("control", ["\v", "\f", "\x85"])
def test_person_line_view_does_not_disable_numeric_control_injection_detection(control):
    source = "성명: 김다은" + control + "전화: 010-1234" + control + "5678"
    result = Anonymizer(strategy="redact", include=["PERSON", "PHONE"]).process(source)
    assert result.text == "성명: [성명]" + control + "전화: [전화번호]"
