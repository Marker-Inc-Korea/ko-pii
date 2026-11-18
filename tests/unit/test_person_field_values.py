"""A bounded person-name field must not lose name syllables as particles."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json, detect_all
from ko_pii.cli import main
from ko_pii.context.context_rules import _has_field_label_before
from ko_pii.context.name_fields import name_role_before
from ko_pii.io_ import read_text
from ko_pii.patterns.person import detect


NAMES = [
    "김다은", "이지은", "박보라", "김태성", "김명부", "이예로", "남궁다은", "유나",
    "김빛나라", "서가람이",
]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("label", ["성명", "성함", "이름", "신청인"])
def test_bounded_field_keeps_the_entire_name(label, name):
    source = label + ": " + name
    found = list(detect(source))
    assert [(d.text, d.start, d.end) for d in found] == [(name, len(label) + 2, len(source))]
    assert Anonymizer(include=["PERSON"], strategy="redact").process(source).text == label + ": [성명]"


@pytest.mark.parametrize("label", ["성명", "성함"])
@pytest.mark.parametrize("name", ["조성", "김성", "김군"])
def test_person_specific_field_is_stronger_than_generic_word_or_suffix_heuristics(label, name):
    assert [d.text for d in detect(label + ": " + name)] == [name]


@pytest.mark.parametrize("prefix,suffix", [
    ("성명: ", ""), ("성 명 = ", "\n주소: 서울"), ("이 름\t", ";"),
    ("성명(한글): ", "\t연락처: 010-1234-5678"),
    ("성명: \"", "\""), ("성함: ", " 연락처: 010-1234-5678"),
    ("성명:\n", ""), ("성명\n", ""),
])
def test_field_markers_and_boundaries_are_not_part_of_the_name(prefix, suffix):
    source = prefix + "김다은" + suffix
    found = detect_all(source, include=["PERSON"])
    assert [(d.text, d.start, d.end) for d in found] == [("김다은", len(prefix), len(prefix) + 3)]


@pytest.mark.parametrize("name", ["김다은", "김태성", "박보라", "남궁다은", "조성", "김빛나라"])
@pytest.mark.parametrize("particle", ["이", "에게", "에게서"])
def test_field_evidence_preserves_the_name_in_earlier_and_later_mentions(name, particle):
    source = name + ".\n성명: " + name + "\n" + name + particle + " 서류를 전달했다."
    found = [d for d in detect(source) if d.text == name]
    assert len(found) == 3
    assert all(source[d.start:d.end] == name for d in found)
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == "[성명].\n성명: [성명]\n[성명]" + particle + " 서류를 전달했다."


@pytest.mark.parametrize("text", [
    "성명서: 김태성", "파일이름: 김태성", "작명이름: 김태성", "대리인수: 김태성",
    "성명 설명: 김태성", "이름 변경: 김태성", "성명: 없음\n김태성",
])
def test_label_substrings_and_other_fields_do_not_grant_name_field_evidence(text):
    assert _has_field_label_before(text, text.index("김태성")) is None


@pytest.mark.parametrize("text", [
    "이름: 당귀, 효능: 보혈", "이름: 인삼", "이름: 삼성", "신청인: 주식회사",
    "성명: 없음", "성명: 미상", "성명: 비공개", "성명: 미기재", "성명: 해당없음",
    "성명\n주소\n서울", "성명: 연락처", "성명: 이름",
])
def test_generic_names_and_empty_value_markers_do_not_become_people(text):
    assert detect_all(text, include=["PERSON"]) == []


@pytest.mark.parametrize("form", ["NFC", "NFD"])
@pytest.mark.parametrize("name", ["김다은", "김태성", "조성", "김빛나라"])
def test_original_offsets_tokenization_and_vault_roundtrip(name, form):
    raw = unicodedata.normalize(form, name)
    prefix, suffix = "\ufb01 성명: ", " | next"
    source = prefix + raw + suffix
    vault = ReversibleVault(salt="name-fields", secret_key="test", fingerprint_iterations=1)
    engine = Anonymizer(include=["PERSON"], vault=vault)
    result = engine.process(source)
    assert result.text == prefix + "<PERSON_1>" + suffix
    detection = result.detections[0].detection
    assert (detection.start, detection.end, detection.text) == (len(prefix), len(prefix) + len(raw), raw)
    assert vault.reveal("<PERSON_1>") == raw
    assert engine.process(source).text == result.text


def test_scoped_exclusions_still_override_explicit_person_fields():
    text = "성명: 김다은"
    scoped = Anonymizer(strategy="redact", include=["PERSON"], person_exclusions=["김다은"])
    assert scoped.process(text).text == text
    assert Anonymizer(strategy="redact", include=["PERSON"]).process(text).text == "성명: [성명]"


def test_narrative_particles_and_audit_policy_keep_their_meaning():
    assert [d.text for d in detect("성명: 홍길동이 신청서를 제출했다.") if d.text.startswith("홍")] == ["홍길동"]
    assert [d.text for d in detect("장혁이 웃었다.") if d.text.startswith("장")] == ["장혁"]
    source = "성명: 김다은"
    result = Anonymizer(mode=ProcessingMode.AUDIT, include=["PERSON"]).process(source)
    assert result.text == source and not result.substitutions


@pytest.mark.parametrize("name", ["쥬하린", "뮈도윤"])
def test_prose_role_retains_unknown_surname_candidates_without_becoming_a_literal_field(name):
    source = "계약의 당사자인 " + name + "은(는) 내용을 확인했습니다."
    found = [d for d in detect(source) if d.text == name]
    assert len(found) == 1
    assert found[0].extra["particle"] == "은"
    assert "pos:name_role(당사자)" in found[0].evidence
    assert "pattern:person_name_field" not in found[0].evidence


@pytest.mark.parametrize("prefix", ["파일이름인 ", "당사자명인 ", "신청인명이 ", "성명서인 "])
def test_role_substrings_do_not_relax_surname_checks(prefix):
    assert name_role_before(prefix + "쥬하린", len(prefix)) is None


def test_ambiguous_particle_at_a_bounded_field_end_is_masked_with_the_value():
    # The field alone cannot prove whether the final syllable is a name or a particle.
    source = "성명: 홍길동이\n다음 항목"
    assert Anonymizer(include=["PERSON"], strategy="redact").process(source).text == "성명: [성명]\n다음 항목"


def test_structured_text_does_not_require_repeating_the_known_field_as_a_schema():
    source = {"note": "성명: 김다은", "other": "public"}
    result = anonymize_json(source, anonymizer=Anonymizer(include=["PERSON"], strategy="redact"))
    assert result.data == {"note": "성명: [성명]", "other": "public"}


@pytest.mark.parametrize("extension", ["txt", "md", "log"])
def test_cli_and_file_reader_keep_distinct_korean_field_rows(tmp_path, extension):
    source = "성명: 김다은\n성명: 김태성\n성명: 박보라"
    path, output, vault_path = [tmp_path / name for name in ("input." + extension, "output.txt", "vault.json")]
    path.write_bytes(source.encode("utf-8"))
    assert read_text(str(path)) == source
    assert main([str(path), "--include", "PERSON", "--vault", str(vault_path), "-o", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == "성명: <PERSON_1>\n성명: <PERSON_2>\n성명: <PERSON_3>"
    vault = ReversibleVault.load(vault_path)
    assert [vault.reveal("<PERSON_" + str(i) + ">") for i in range(1, 4)] == ["김다은", "김태성", "박보라"]
