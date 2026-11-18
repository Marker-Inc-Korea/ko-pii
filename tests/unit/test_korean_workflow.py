"""Business text has the same protection through public processing paths."""
import json

import pytest

from ko_pii import Anonymizer, PolicyProfile, PreForwardAnonymizer, anonymize_json
from ko_pii.cli import main


SOURCE = ("담당자는 김다은입니다.\u2028"
          "주소: 서울특별시 강남구 테헤란로 152 (101동 1202호, 010-1234-5678)")
EXPECTED = "담당자는 [성명]입니다.\u2028주소: [주소][전화번호][주소]"


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
