"""Business text has the same protection through public processing paths."""
import json

import pytest

from ko_pii import Anonymizer, PolicyProfile, PreForwardAnonymizer, anonymize_json
from ko_pii.cli import main


SOURCE = ("담당자는 김다은입니다.\u2028"
          "주소: 서울특별시 강남구 테헤란로 152 (101동 1202호, 010-1234-5678)")
EXPECTED = "담당자는 [성명]입니다.\u2028주소: [주소][전화번호][주소]"
MULTILINGUAL_SOURCE = "성명: __John Smith__\u2028성명: 김민수(金民秀)\n성명: 장피에르뒤퐁\nJohn Smith"
MULTILINGUAL_EXPECTED = "성명: __[성명]__\u2028성명: [성명]([성명])\n성명: [성명]\n[성명]"
FORM_SOURCE = "성명: 김빛나라 **전화번호**: 010-1234-5678 생년월일(양력): 1988-01-01"
FORM_EXPECTED = "성명: [성명] **전화번호**: [전화번호] 생년월일(양력): [생년월일]"


def test_business_text_through_api_json_profile_and_every_transport_split():
    assert Anonymizer(strategy="redact").process(SOURCE).text == EXPECTED
    assert anonymize_json({"note": SOURCE}, anonymizer=Anonymizer(strategy="redact")).data == {
        "note": EXPECTED,
    }
    profile = PolicyProfile({"strategy": "redact"})
    assert profile.process(SOURCE).text == EXPECTED
    assert profile.process_json({"note": SOURCE}).data == {"note": EXPECTED}
    for split in range(len(SOURCE) + 1):
        buffered = PreForwardAnonymizer(Anonymizer(strategy="redact"))
        buffered.feed(SOURCE[:split])
        buffered.feed(SOURCE[split:])
        assert buffered.finalize().text == EXPECTED


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_business_text_through_cli_and_value_free_explanation(tmp_path, fmt):
    source = tmp_path / ("input.txt" if fmt == "text" else "input.json")
    output = tmp_path / "output.txt"
    report = tmp_path / "explanation.json"
    body = SOURCE if fmt == "text" else json.dumps({"note": SOURCE}, ensure_ascii=False)
    source.write_bytes(body.encode("utf-8"))
    assert main([str(source), "--format", fmt, "--strategy", "redact",
                 "--output", str(output), "--explain", str(report), "--trace-limit", "20"]) == 0
    rendered = output.read_text(encoding="utf-8")
    if fmt == "text":
        assert rendered == EXPECTED
    else:
        assert json.loads(rendered) == {"note": EXPECTED}
    explanation = report.read_text(encoding="utf-8")
    assert "protection.overlap-remainder.v1" in explanation
    assert all(value not in explanation for value in ("김다은", "테헤란로", "010-1234-5678", "1202"))


def test_multilingual_literal_fields_share_api_json_profile_and_buffered_results():
    profile = PolicyProfile({"strategy": "redact", "include": ["PERSON"]})
    assert profile.process(MULTILINGUAL_SOURCE).text == MULTILINGUAL_EXPECTED
    assert profile.process_json({"note": MULTILINGUAL_SOURCE}).data == {"note": MULTILINGUAL_EXPECTED}
    for split in range(len(MULTILINGUAL_SOURCE) + 1):
        buffered = PreForwardAnonymizer(Anonymizer(strategy="redact", include=["PERSON"]))
        buffered.feed(MULTILINGUAL_SOURCE[:split])
        buffered.feed(MULTILINGUAL_SOURCE[split:])
        assert buffered.finalize().text == MULTILINGUAL_EXPECTED


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_multilingual_literal_fields_through_cli_and_value_free_explanation(tmp_path, fmt):
    source = tmp_path / ("input.txt" if fmt == "text" else "input.json")
    output = tmp_path / "output.txt"
    report = tmp_path / "explanation.json"
    body = MULTILINGUAL_SOURCE if fmt == "text" else json.dumps({"note": MULTILINGUAL_SOURCE}, ensure_ascii=False)
    source.write_bytes(body.encode("utf-8"))
    assert main([str(source), "--format", fmt, "--strategy", "redact",
                 "--output", str(output), "--explain", str(report), "--trace-limit", "20"]) == 0
    rendered = output.read_text(encoding="utf-8")
    assert (rendered if fmt == "text" else json.loads(rendered)["note"]) == MULTILINGUAL_EXPECTED
    explanation = report.read_text(encoding="utf-8")
    assert '"rule_id": "ko-pii.person.v1"' in explanation
    assert "pattern:person_literal_name_field" not in explanation
    assert all(value not in explanation for value in ("John Smith", "김민수", "金民秀", "장피에르뒤퐁"))


def test_one_line_form_through_api_json_profile_and_buffered_chunks():
    profile = PolicyProfile({"strategy": "redact"})
    assert profile.process(FORM_SOURCE).text == FORM_EXPECTED
    assert profile.process_json({"note": FORM_SOURCE}).data == {"note": FORM_EXPECTED}
    for split in range(len(FORM_SOURCE) + 1):
        buffered = PreForwardAnonymizer(Anonymizer(strategy="redact"))
        buffered.feed(FORM_SOURCE[:split])
        buffered.feed(FORM_SOURCE[split:])
        assert buffered.finalize().text == FORM_EXPECTED


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_one_line_form_through_cli(tmp_path, fmt):
    source = tmp_path / ("input.txt" if fmt == "text" else "input.json")
    output = tmp_path / "output.txt"
    body = FORM_SOURCE if fmt == "text" else json.dumps({"note": FORM_SOURCE}, ensure_ascii=False)
    source.write_bytes(body.encode("utf-8"))
    assert main([str(source), "--format", fmt, "--strategy", "redact", "--output", str(output)]) == 0
    rendered = output.read_text(encoding="utf-8")
    assert (rendered if fmt == "text" else json.loads(rendered)["note"]) == FORM_EXPECTED
