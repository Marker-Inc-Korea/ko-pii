import json

import pytest

from ko_pii import Anonymizer, EACH, FieldRule, anonymize_json, anonymize_jsonl
from ko_pii.cli import main
from ko_pii.field_rules import rules_from_json


def test_repeated_nested_arrays_and_optional_field():
    data = {"groups": [{"users": [{"name": "이상"}, {"name": "홍길동", "phone": "018-2345-6789"}]}]}
    rules = [FieldRule(("groups", EACH, "users", EACH, "name"), "PERSON"),
             FieldRule(("groups", EACH, "users", EACH, "phone"), "PHONE", required=False)]
    result = anonymize_json(data, anonymizer=Anonymizer(strategy="redact"), field_rules=rules)
    users = result.data["groups"][0]["users"]
    assert users == [{"name": "[성명]"}, {"name": "[성명]", "phone": "[전화번호]"}]
    assert data["groups"][0]["users"][0]["name"] == "이상"
    assert result.report()["field_rules"][1]["missing"] == 1
    assert result.report()["field_rules"][0]["matched"] == 2


def test_literal_star_and_pointer_escaping():
    result = anonymize_json({"*": {"a/b": {"~": "이상"}}},
                            field_rules=[FieldRule(("*", "a/b", "~"), "PERSON")])
    assert result.data["*"]["a/b"]["~"] == "<PERSON_1>"
    assert result.fields[0].path == "/*/a~1b/~0"


def test_optional_missing_parent_and_empty_array_are_reported():
    rules = [FieldRule(("user", "name"), "PERSON", required=False)]
    rows = anonymize_jsonl('{"user":{"name":"이상"}}\n{"event":"heartbeat"}', field_rules=rules)
    assert rows[1].field_rule_summary[0]["missing"] == 1
    result = anonymize_json({"users": []}, field_rules=[FieldRule(("users", EACH, "name"), "PERSON")])
    assert result.field_rule_summary[0]["empty_arrays"] == 1
    assert not result.fields


@pytest.mark.parametrize("data, rule", [
    ({"users": [{"name": "x"}, {}]}, FieldRule(("users", EACH, "name"), "PERSON")),
    ({"users": {}}, FieldRule(("users", EACH, "name"), "PERSON", required=False)),
    ({"name": 1.2}, FieldRule(("name",), "PERSON")),
    ({"user": None}, FieldRule(("user", "name"), "PERSON", required=False)),
])
def test_all_rule_validation_precedes_vault_writes(data, rule):
    anon = Anonymizer()
    with pytest.raises(ValueError):
        anonymize_json(data, anonymizer=anon, field_rules=[rule])
    assert not anon.vault.entries()


def test_jsonl_all_rules_preflight_before_first_row():
    anon = Anonymizer()
    with pytest.raises(ValueError, match="line 2"):
        anonymize_jsonl('{"name":"이상"}\n{}', anonymizer=anon,
                        field_rules=[FieldRule(("name",), "PERSON")])
    assert not anon.vault.entries()


def test_conflicts_filters_indices_root_and_null():
    with pytest.raises(ValueError, match="conflicting"):
        anonymize_json({"x": "x"}, field_labels={"/x": "PERSON"}, field_rules=[FieldRule(("x",), "EMAIL")])
    with pytest.raises(ValueError, match="conflicts"):
        anonymize_json({}, anonymizer=Anonymizer(exclude=["PERSON"]),
                        field_rules=[FieldRule(("x",), "PERSON", required=False)])
    result = anonymize_json([None, 123], field_rules=[FieldRule((0,), "PERSON"), FieldRule((1,), "ACCOUNT")])
    assert result.data == [None, "<ACCOUNT_1>"]
    assert result.field_rule_summary[0]["null_fields"] == 1
    assert anonymize_json("이상", field_rules=[FieldRule((), "PERSON")]).data == "<PERSON_1>"


@pytest.mark.parametrize("data", [None, [{"path": "x", "label": "PERSON"}],
                                     [{"path": [True], "label": "PERSON"}],
                                     [{"path": [], "label": "TYPO"}],
                                     [{"path": [], "label": "PERSON", "required": 1}]])
def test_bad_config(data):
    with pytest.raises(ValueError):
        rules_from_json(data)


def test_cli_field_rules_and_collision(tmp_path, capsys):
    source, config, output = [tmp_path / name for name in ("in.json", "rules.json", "out.json")]
    source.write_text('{"users":[{"name":"이상"},{}]}', encoding="utf-8")
    config.write_text(json.dumps([{"path": ["users", None, "name"], "label": "PERSON", "required": False}]))
    assert main([str(source), "--format", "json", "--field-rules", str(config), "-o", str(output), "--json-summary"]) == 0
    assert json.loads(output.read_text())["users"][0]["name"] == "<PERSON_1>"
    assert json.loads(capsys.readouterr().err)["field_rules"][0]["rules"][0]["missing"] == 1
    before = config.read_bytes()
    with pytest.raises(SystemExit):
        main([str(source), "--format", "json", "--field-rules", str(config), "-o", str(config)])
    assert config.read_bytes() == before
