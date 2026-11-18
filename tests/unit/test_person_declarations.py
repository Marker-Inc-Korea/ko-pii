"""Explicit person-role declarations need not be rewritten as colon fields."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault
from ko_pii.context.name_fields import name_role_before


@pytest.mark.parametrize("name", ["김다은", "박보라", "김태성", "남궁다은", "유나"])
@pytest.mark.parametrize("role", ["신청인", "보호자", "담당자", "작성자", "성명"])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_person_role_and_explicit_copula_preserve_the_full_name(role, name, form):
    topic = "은" if (ord(role[-1]) - 0xAC00) % 28 else "는"
    prefix, ending = role + topic + " ", "입니다."
    raw = unicodedata.normalize(form, name)
    source = prefix + raw + ending
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + "[성명]" + ending
    assert [(r.detection.start, r.detection.end, r.detection.text) for r in result.detections] == [
        (len(prefix), len(prefix) + len(raw), raw),
    ]


@pytest.mark.parametrize("ending", ["이며", "이고", "이라고", "이라는", "이라"])
def test_declaration_endings_do_not_become_part_of_a_three_syllable_name(ending):
    source = "신청인은 김다은" + ending + " 문서에 기재했습니다."
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == "신청인은 [성명]" + ending + " 문서에 기재했습니다."


def test_field_confirmed_names_and_role_declarations_propagate_in_both_directions():
    source = "김다은이며 접수했다.\n작성자는 김다은입니다.\n김다은에게 전달했다."
    engine = Anonymizer(include=["PERSON"])
    result = engine.process(source)
    assert result.text == "<PERSON_1>이며 접수했다.\n작성자는 <PERSON_1>입니다.\n<PERSON_1>에게 전달했다."
    assert len(result.detections) == 3
    restored = ReversibleVault.from_dict(engine.vault.to_dict())
    assert restored.reveal("<PERSON_1>") == "김다은"


def test_literal_field_can_confirm_a_later_copula_without_another_role():
    source = "성명: 김태성\n김태성이며 확인했다."
    assert Anonymizer(include=["PERSON"], strategy="redact").process(source).text == "성명: [성명]\n[성명]이며 확인했다."


@pytest.mark.parametrize("text", [
    "파일이름은 김다은입니다.", "성명서는 김다은입니다.", "담당자는 없음입니다.",
    "이름은 인삼입니다.", "이름은 당귀입니다.", "신청인은 주식회사입니다.",
    "담당자는 운영팀입니다.", "작성자는 기획부서입니다.", "신청인은 삼성전자입니다.",
    "담당자: 운영팀", "작성자: 기획부서", "담당자: 운영팀입니다.",
])
def test_other_headings_placeholder_values_and_generic_terms_are_not_name_declarations(text):
    result = Anonymizer(include=["PERSON"], strategy="redact").process(text)
    assert result.text == text


def test_copula_words_without_a_role_or_confirmed_name_are_not_new_person_evidence():
    source = "김다은이며 김태성이라고 표시했다."
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == source


@pytest.mark.parametrize("prefix,label", [
    ("신청인은 ", "신청인"), ("신청인이 ", "신청인"), ("보호자가 ", "보호자"),
    ("담당자는 ", "담당자"), ("작성자인 ", "작성자"),
])
def test_subject_variants_are_bounded_role_markers(prefix, label):
    assert name_role_before(prefix + "김다은", len(prefix)) == label


def test_scoped_exclusion_and_audit_still_override_role_declarations():
    source = "담당자는 김다은입니다."
    scoped = Anonymizer(include=["PERSON"], person_exclusions=["김다은"])
    assert scoped.process(source).text == source and not scoped.vault.entries()
    audit = Anonymizer(include=["PERSON"], mode=ProcessingMode.AUDIT)
    result = audit.process(source)
    assert result.text == source and not result.substitutions and not audit.vault.entries()


@pytest.mark.parametrize("name", ["김하이라", "남궁이라"])
def test_a_literal_full_name_that_ends_like_a_copula_is_not_truncated(name):
    source = "성명: " + name + "\n담당자는 " + name + "입니다."
    assert Anonymizer(include=["PERSON"], strategy="redact").process(source).text == "성명: [성명]\n담당자는 [성명]입니다."
