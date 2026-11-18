"""A following form key is not part of a name or a reason to leave it clear."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ReversibleVault, detect_all
from ko_pii.context.name_fields import next_field_after_name


NAMES = ["김빛나라", "남궁다은", "장피에르뒤퐁", "김 민수", "John Smith", "金民秀"]
FIELDS = ["전화번호", "휴대폰번호", "이메일", "생년월일", "계좌번호", "여권번호", "사번", "비고", "접수일자", "Phone"]
FRAMES = [("", ""), ("[", "]"), ("【", "】"), ("**", "**"), ("__", "__"), ("`", "`")]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("frame", FRAMES)
def test_following_known_field_does_not_swallow_metadata_or_disable_name_masking(name, field, frame):
    suffix = " " + frame[0] + field + frame[1] + ": public"
    source = "성명: " + name + suffix
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == "성명: [성명]" + suffix
    assert [(item.detection.start, item.detection.end, item.detection.text) for item in result.detections] == [
        (4, 4 + len(name), name),
    ]


@pytest.mark.parametrize("metadata", [
    "생년월일(양력): public", "생년월일(음력): public", "연락처(회사): public",
    "**전화번호(업무용)**: public", "__연락처__(회사): public",
    "[생년월일(YYYY-MM-DD)]: public", "`phone`(work): public",
    "이메일 = public", "고객 연락처: public", "고객 **전화번호**: public",
    "**고객 전화번호**: public", "customer_email: public", "patient_`birth_date`: public",
])
@pytest.mark.parametrize("name", ["김빛나라", "장피에르뒤퐁", "John Smith"])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_qualified_following_field_preserves_raw_spans_and_vault_boundary(name, metadata, form):
    raw = unicodedata.normalize(form, name)
    prefix = unicodedata.normalize(form, "성명: ")
    suffix = " " + unicodedata.normalize(form, metadata)
    source = prefix + raw + suffix
    vault = ReversibleVault(salt="form-boundary", secret_key="test", fingerprint_iterations=1)
    result = Anonymizer(include=["PERSON"], vault=vault).process(source)
    assert result.text == prefix + "<PERSON_1>" + suffix
    assert vault.reveal("<PERSON_1>") == raw
    assert [(item.detection.start, item.detection.end) for item in result.detections] == [
        (len(prefix), len(prefix) + len(raw)),
    ]


@pytest.mark.parametrize("tail", [
    " 전화번호부: public", " 생년월일설명: public", " UnknownField: public",
    " __전화번호**: public", " **전화번호__: public", " [전화번호: public",
    " 전화번호 public", "\n전화번호: public", "\t전화번호: public",
    " 전화번호(회\n사): public", " 전화번호(회\t사): public",
    " 전화번호((회사)): public", " 전화번호(" + "x" * 33 + "): public",
    " 고객\n전화번호: public", " 고객\t전화번호: public", " customerEmail: public",
])
def test_boundary_recognition_does_not_guess_unknown_or_broken_field_syntax(tail):
    assert not next_field_after_name("John Smith" + tail, len("John Smith"))


def test_qualifier_bound_is_inclusive_and_does_not_change_general_name_rules():
    assert next_field_after_name(" 전화번호(" + "x" * 32 + "): public", 0)
    assert detect_all("이름: 인삼 전화번호: 010-1234-5678", include=["PERSON"]) == []


def test_metadata_boundary_does_not_grant_person_evidence_to_its_value():
    found = detect_all("성명: 없음 생년월일: 박보라", include=["PERSON"])
    assert all("pattern:person_name_field" not in item.evidence for item in found)
