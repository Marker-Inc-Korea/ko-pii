import copy
import io
import json
import os

import pytest

from ko_pii.policy_preview import compare_json_policies, main


def test_field_exclusion_is_local_and_assertion_wins_without_leaking_values():
    data = {"product-private": "성명: 홍길동", "customer-private": "홍길동"}
    before = {"include": ["PERSON"], "field_labels": {"/customer-private": "PERSON"}}
    after = {**before, "field_person_exclusions": {
        "/product-private": ["홍길동"], "/customer-private": ["홍길동"],
    }}
    originals = copy.deepcopy((data, before, after))
    report = compare_json_policies(data, before=before, after=after)
    assert (data, before, after) == originals
    assert report["observed_span_count"] == 2
    assert report["changed_span_count"] == 1
    assert report["changed_by_label"] == {"PERSON": 1}
    assert report["changes"][0]["field_index"] == 0
    assert report["changes"][0]["before"]["output_state"] == "replaced"
    assert report["changes"][0]["after"]["output_state"] == "not_detected"
    assert report["fields"][1]["after_output_counts"] == {"replaced": 1}
    assert report["before_policy_sha256"] != report["after_policy_sha256"]
    serialized = json.dumps(report, ensure_ascii=False)
    for private in ("홍길동", "product-private", "customer-private", "<PERSON_1>"):
        assert private not in serialized
    assert not report["paths_included"]
    assert not report["keys_screened"]
    assert not report["whole_text_safety_assessed"]


@pytest.mark.parametrize("strategy", ["tokenize", "hashed", "fpe", "partial", "redact", "asterisk"])
def test_identical_json_policies_ignore_generated_replacement_values(strategy):
    policy = {"include": ["PHONE", "EMAIL"], "strategy": strategy}
    report = compare_json_policies(["user@example.com", "010-2345-6789"], before=policy, after=policy)
    assert report["changed_span_count"] == 0
    assert report["observed_span_count"] == 2
    assert report["before_policy_sha256"] == report["after_policy_sha256"]


def test_fresh_vault_per_side(monkeypatch):
    import ko_pii.policy_preview as preview
    original = preview.anonymize_json
    vaults = []

    def observed(*args, **kwargs):
        vault = kwargs["anonymizer"].vault
        assert len(vault) == 0
        vaults.append(vault)
        return original(*args, **kwargs)

    monkeypatch.setattr(preview, "anonymize_json", observed)
    compare_json_policies(["user@example.com"] * 2, before={}, after={})
    assert len(vaults) == 2 and vaults[0] is not vaults[1]
    assert len(vaults[0]) == len(vaults[1]) == 1


def test_integer_assertion_aligns_same_fields_when_only_one_policy_screens_it():
    data = {"skip": 42, "account": 12345, "email": "user@example.com", "boolean": True, "null": None, "float": 1.5}
    plain = {"include": ["EMAIL", "ACCOUNT"]}
    asserted = {**plain, "field_labels": {"/account": "ACCOUNT"}}
    report = compare_json_policies(data, before=plain, after=asserted, include_paths=True)
    assert [r["field_index"] for r in report["fields"]] == [1, 2]
    assert [r["path"] for r in report["fields"]] == ["/account", "/email"]
    assert report["compared_field_count"] == 2
    assert report["fields"][0]["before_screened"] is False
    assert report["fields"][0]["after_screened"] is True
    assert report["fields"][1]["before_screened"] is True
    assert report["observed_span_count"] == 2
    assert report["changed_by_label"] == {"ACCOUNT": 1}
    change = report["changes"][0]
    assert change["source_span"] == [0, 5]
    assert change["before"]["output_state"] == "not_detected"
    assert change["after"]["output_state"] == "replaced"
    reverse = compare_json_policies(data, before=asserted, after=plain)
    assert reverse["changes"][0]["before"] == change["after"]
    assert reverse["changes"][0]["after"] == change["before"]
    assert reverse["unasserted_numbers_screened"] is False


@pytest.mark.parametrize("value", [12345, "12345"])
def test_root_scalar_and_within_field_offsets(value):
    before = {"include": ["ACCOUNT"]}
    after = {**before, "field_labels": {"": "ACCOUNT"}}
    report = compare_json_policies(value, before=before, after=after, include_paths=True)
    assert report["changes"][0]["path"] == ""
    assert report["changes"][0]["source_span"] == [0, 5]
    assert report["offset_unit"] == "python_code_points_within_field"


def test_array_rules_escaped_paths_optional_fields_and_nulls():
    data = {"a/b": {"~": [{"id": 123}, {"id": None}, {"id": 456}, {}]}}
    before = {"include": ["ACCOUNT"]}
    after = {**before, "field_rules": [{"path": ["a/b", "~", None, "id"], "label": "ACCOUNT", "required": False}]}
    report = compare_json_policies(data, before=before, after=after, include_paths=True)
    assert report["changed_span_count"] == 2
    assert [r["path"] for r in report["changes"]] == ["/a~1b/~0/0/id", "/a~1b/~0/2/id"]
    assert report["before_output_counts"] == {"not_detected": 2}
    assert report["after_output_counts"] == {"replaced": 2}


@pytest.mark.parametrize("config", [
    {"vault": object()}, {"secondary_detector": object()}, {"trace_limit": 1},
    {"field_labels": {"/name": "PESRON"}}, {"field_labels": {"name": "PERSON"}},
    {"field_labels": {"/~2": "PERSON"}}, {"field_labels": {"/name": "PERSON"}, "exclude": ["PERSON"]},
    {"field_rules": [{"path": ["name"], "label": "PERSON"}], "include": ["EMAIL"]},
    {"field_rules": [{"path": [True], "label": "PERSON"}]}, {"field_rules": None},
    {"field_person_exclusions": {"/name": "private"}}, {"field_person_exclusions": {"name": ["private"]}},
])
def test_invalid_settings_rejected_without_reflecting_values(config):
    with pytest.raises(ValueError) as error:
        compare_json_policies({"name": "private-value"}, before={}, after=config)
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize("config", [
    {"field_labels": {"/missing-secret": "PERSON"}},
    {"field_person_exclusions": {"/missing-secret": ["private-value"]}},
    {"field_rules": [{"path": ["missing-secret"], "label": "PERSON"}]},
    {"field_labels": {"/name": "EMAIL"}, "field_rules": [{"path": ["name"], "label": "PERSON"}]},
])
def test_invalid_document_binding_rejected_without_paths_or_values(config):
    with pytest.raises(ValueError) as error:
        compare_json_policies({"name": "private-value"}, before={}, after=config)
    assert "missing-secret" not in str(error.value)
    assert "private-value" not in str(error.value)


@pytest.mark.parametrize("data", [None, True, 1.2, [], {}, {"empty": ""}])
def test_no_observed_spans_is_not_safety_approval(data):
    report = compare_json_policies(data, before={}, after={})
    assert report["observed_span_count"] == 0
    assert report["whole_text_safety_assessed"] is False
    assert report["scope"] == "union_of_observed_spans_not_gold"


@pytest.mark.parametrize("data", ["x" * 100_001, [""] * 1001, "\ud800", {"\ud800": ""}, float("nan"), {1: "x"}],
                         ids=["long-text", "many-fields", "surrogate-value", "surrogate-key", "nonfinite", "invalid-key"])
def test_bounds_and_invalid_json_values(data):
    with pytest.raises(ValueError):
        compare_json_policies(data, before={}, after={})


def test_cycles_and_span_bound():
    data = []
    data.append(data)
    with pytest.raises(ValueError, match="cycle"):
        compare_json_policies(data, before={}, after={})
    with pytest.raises(ValueError, match="2000"):
        compare_json_policies(["user@example.com " * 1001] * 2,
                              before={"include": ["EMAIL"]}, after={"include": ["EMAIL"]})


def test_paths_must_be_explicit_boolean():
    with pytest.raises(ValueError, match="boolean"):
        compare_json_policies({}, before={}, after={}, include_paths="false")


def test_cli_json_output_and_source_protection(tmp_path, capsys, monkeypatch):
    source, before, after, output = [tmp_path / name for name in ("source.json", "before.json", "after.json", "report.json")]
    source.write_text('{"private-field": "user@example.com"}')
    before.write_text('{"mode":"AUDIT"}')
    after.write_text('{}')
    originals = [path.read_bytes() for path in (source, before, after)]
    args = [str(source), "--format", "json", "--before", str(before), "--after", str(after)]
    assert main(args + ["--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["changed_span_count"] == 1
    assert "private-field" not in output.read_text()
    assert "user@example.com" not in output.read_text()
    assert main(args + ["--include-paths"]) == 0
    assert json.loads(capsys.readouterr().out)["changes"][0]["path"] == "/private-field"
    for path in (source, before, after):
        assert main(args + ["--output", str(path)]) == 1
    alias = tmp_path / "alias.json"
    os.link(source, alias)
    assert main(args + ["--output", str(alias)]) == 1
    assert [path.read_bytes() for path in (source, before, after)] == originals
    monkeypatch.setattr("sys.stdin", io.StringIO(source.read_text()))
    assert main(["-", *args[1:]]) == 0
    assert json.loads(capsys.readouterr().out)["changed_span_count"] == 1


@pytest.mark.parametrize("contents", ['{"x":1,"x":2}', '{"x":', '{"x":"\\ud800"}', '{"x": NaN}'])
def test_cli_invalid_json_has_sanitized_error_and_no_output(tmp_path, capsys, contents):
    source, settings, output = [tmp_path / name for name in ("source.json", "settings.json", "output.json")]
    source.write_text(contents)
    settings.write_text('{}')
    assert main([str(source), "--format", "json", "--before", str(settings),
                 "--after", str(settings), "--output", str(output)]) == 1
    assert not output.exists()
    assert contents not in capsys.readouterr().err


def test_cli_paths_only_for_json():
    with pytest.raises(SystemExit) as error:
        main(["input.txt", "--before", "a.json", "--after", "b.json", "--include-paths"])
    assert error.value.code == 2
