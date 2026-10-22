import copy
import json

import pytest

from ko_pii import Anonymizer, ProcessingMode, StructuredLimits, anonymize_json, anonymize_jsonl, loads_json
from ko_pii.cli import main


def test_nested_shape_and_original_preserved():
    data = {"users": [{"email": "user@example.com", "phone": "010-2345-6789", "n": 3}], "yes": True, "none": None}
    original = copy.deepcopy(data)
    result = anonymize_json(data, anonymizer=Anonymizer(strategy="redact", strategies={"PHONE": "partial"}))
    assert data == original
    assert result.data["users"][0]["email"] == "[이메일]"
    assert result.data["users"][0]["phone"] == "010-****-6789"
    assert result.data["users"][0]["n"] == 3
    assert result.data["yes"] is True and result.data["none"] is None
    assert result.fields[0].path == "/users/0/email"
    assert result.data is not data and result.data["users"] is not data["users"]


def test_pointer_escaping_assertions_and_repeated_tokens():
    data = {"a/b": {"~name": "이상"}, "again": "이상", "id": 12345}
    result = anonymize_json(data, field_labels={"/a~1b/~0name": "PERSON", "/again": "PERSON", "/id": "ACCOUNT"})
    assert result.data["a/b"]["~name"] == result.data["again"] == "<PERSON_1>"
    assert result.data["id"] == "<ACCOUNT_1>"
    assert result.report()["fields"][0]["findings"][0]["rule_id"] == "field.asserted.v1"


def test_audit_preserves_integer_type():
    result = anonymize_json({"id": 1234}, field_labels={"/id": "ACCOUNT"},
                            anonymizer=Anonymizer(mode=ProcessingMode.AUDIT))
    assert result.data == {"id": 1234}


def test_keys_and_paths_are_explicitly_not_screened():
    key = "user@example.com"
    result = anonymize_json({key: "010-2345-6789"}, anonymizer=Anonymizer(strategy="redact"))
    assert key in result.data
    assert key not in json.dumps(result.report())
    assert result.report()["keys_screened"] is False
    assert result.report(include_paths=True)["fields"][0]["path"] == "/" + key


@pytest.mark.parametrize("data, labels", [
    ({"a": 1.2}, {"/a": "ACCOUNT"}), ({"a": True}, {"/a": "ACCOUNT"}),
    ({"a": {}}, {"/a": "PERSON"}), ({}, {"/missing": "PHONE"}),
    ({"a": "x"}, {"a": "PERSON"}), ({"a": "x"}, {"/~2": "PERSON"}),
    ({"a": "x"}, {"/a": "TYPO"}),
])
def test_invalid_field_policies_fail_before_vault_writes(data, labels):
    anon = Anonymizer()
    with pytest.raises(ValueError):
        anonymize_json(data, anonymizer=anon, field_labels=labels)
    assert not anon.vault.entries()


def test_conflicting_filter_rejected():
    with pytest.raises(ValueError, match="conflicts"):
        anonymize_json({"a": "name"}, anonymizer=Anonymizer(exclude=["PERSON"]), field_labels={"/a": "PERSON"})


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"secret": NaN}', '{"secret": 1e999}', '"\\ud800"', '{bad'])
def test_strict_json_rejects_invalid_without_values(text):
    with pytest.raises(ValueError) as exc:
        loads_json(text)
    assert "secret" not in str(exc.value)


def test_bounds_and_cycles():
    data = []
    data.append(data)
    with pytest.raises(ValueError, match="cycle"):
        anonymize_json(data)
    with pytest.raises(ValueError, match="depth"):
        anonymize_json([[["a"]]], limits=StructuredLimits(max_depth=2))
    with pytest.raises(ValueError, match="node"):
        anonymize_json([1, 2, 3], limits=StructuredLimits(max_nodes=3))
    with pytest.raises(ValueError, match="character"):
        anonymize_json("abcd", limits=StructuredLimits(max_string_chars=3))
    with pytest.raises(ValueError):
        anonymize_json({1: "x"})


def test_jsonl_validate_all_before_processing_and_line_numbers():
    anon = Anonymizer()
    with pytest.raises(ValueError, match="line 3"):
        anonymize_jsonl('{"a":"user@example.com"}\n\n{bad', anonymizer=anon)
    assert not anon.vault.entries()
    rows = anonymize_jsonl('{"a":"user@example.com"}\n\n{"a":"user@example.com"}', anonymizer=anon)
    assert [r.source_line for r in rows] == [1, 3]
    assert rows[0].data == rows[1].data == {"a": "<EMAIL_1>"}


def test_unicode_line_separator_inside_json_string_is_not_a_record_boundary():
    text = json.dumps({"message": "앞\u2028user@example.com\u2028뒤"}, ensure_ascii=False)
    result = anonymize_jsonl(text, anonymizer=Anonymizer(strategy="redact", include=["EMAIL"]))
    assert len(result) == 1
    assert result[0].data["message"] == "앞\u2028[이메일]\u2028뒤"


def test_json_cli_and_value_free_explanation(tmp_path, capsys):
    source, target, report = [tmp_path / s for s in ("input.json", "output.json", "report.json")]
    source.write_text(json.dumps({"items": [{"email": "user@예시.kr", "id": 12345}]}), encoding="utf-8")
    assert main([str(source), "--format", "json", "-s", "redact", "--field-label", "/items/0/id=ACCOUNT",
                 "--strategy-for", "EMAIL=asterisk", "-o", str(target), "--explain", str(report), "--json-summary"]) == 0
    result = json.loads(target.read_text("utf-8"))
    assert result["items"][0]["id"] == "[계좌번호]"
    assert "@" not in result["items"][0]["email"]
    assert "user@" not in report.read_text("utf-8")
    assert json.loads(capsys.readouterr().err)["keys_screened"] is False


def test_jsonl_cli_failure_keeps_existing_output(tmp_path, capsys):
    source, target = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    source.write_text('{"a":"user@example.com"}\n{"a":1,"a":2}', encoding="utf-8")
    target.write_text("existing", encoding="utf-8")
    assert main([str(source), "--format", "jsonl", "-o", str(target)]) == 1
    assert target.read_text("utf-8") == "existing"
    assert "user@example.com" not in capsys.readouterr().err


def test_explanation_path_cannot_overwrite_input(tmp_path):
    source = tmp_path / "in.txt"
    source.write_text("hello", encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(source), "--explain", str(source)])
    assert source.read_text("utf-8") == "hello"
