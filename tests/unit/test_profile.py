from dataclasses import FrozenInstanceError
import json

import pytest

from ko_pii import PolicyProfile, StructuredLimits
from ko_pii.cli import main
from ko_pii.policy_preview import compare_policies, compare_json_policies


def test_round_trip_detached_and_hidden_repr():
    settings = {"strategy": "redact", "include": ["EMAIL"], "person_exclusions": ["private-term"]}
    profile = PolicyProfile(settings, name="private-name")
    settings["include"].append("PERSON")
    exported = profile.to_dict()
    exported["settings"]["include"].append("PERSON")
    assert profile.settings["include"] == ["EMAIL"]
    assert "private" not in repr(profile)
    restored = PolicyProfile.from_json(json.dumps(profile.to_dict()))
    assert restored == profile
    assert restored.fingerprint == profile.fingerprint
    assert PolicyProfile(profile.settings, name="other").fingerprint == profile.fingerprint
    with pytest.raises(FrozenInstanceError):
        profile.name = "changed"


def test_fresh_vault_and_preview_same_settings():
    profile = PolicyProfile({"include": ["EMAIL"]})
    a, b = profile.process("a@example.com"), profile.process("b@example.com")
    assert a.text == b.text == "<EMAIL_1>"
    assert a.vault is not b.vault
    report = compare_policies("a@example.com", before=profile, after=profile.to_dict())
    assert report["changed_span_count"] == 0
    assert report["before_policy_sha256"] == profile.fingerprint


def test_structured_profile_and_preview():
    profile = PolicyProfile({"strategy": "redact", "include": ["PERSON"],
                             "field_rules": [{"path": ["users", None, "name"], "label": "PERSON", "required": True}]})
    data = {"users": [{"name": "unusual-name"}]}
    result = profile.process_json(data)
    assert result.data == {"users": [{"name": "[성명]"}]}
    assert profile.process_jsonl(json.dumps(data))[0].data == result.data
    with pytest.raises(ValueError):
        profile.process("unusual-name")
    with pytest.raises(ValueError):
        profile.process_json(data, limits=StructuredLimits(max_chars=1))
    report = compare_json_policies(data, before={}, after=profile)
    assert report["after_policy_sha256"] == profile.fingerprint
    assert "unusual-name" not in json.dumps(report)
    assert report["changed_span_count"] == 1


@pytest.mark.parametrize("value", [
    None, [], {"schema_version": True, "settings": {}}, {"schema_version": 2, "settings": {}},
    {"schema_version": 1}, {"settings": {}}, {"schema_version": 1, "settings": [], "name": "x"},
    {"schema_version": 1, "settings": {}, "extra": 1}, {"include": ["UNKNOWN"]},
    {"strategy": "unknown"}, {"secondary_detector": "anything"}, {"vault": "secret"},
    {"schema_version": 1, "settings": {}, "name": "line\nbreak"},
])
def test_invalid_profiles(value):
    with pytest.raises(ValueError):
        PolicyProfile.from_json(json.dumps(value))


def test_duplicate_keys_and_size():
    with pytest.raises(ValueError):
        PolicyProfile.from_json('{"strategy":"redact","strategy":"tokenize"}')
    with pytest.raises(ValueError):
        PolicyProfile.from_json(" " * 100001)
    with pytest.raises(ValueError):
        PolicyProfile({}, name="\ud800")


@pytest.mark.parametrize("fmt", ["text", "json", "jsonl"])
def test_cli_same_as_python(tmp_path, capsys, fmt):
    profile = PolicyProfile({"strategy": "redact", "include": ["EMAIL"]})
    config = tmp_path / "policy.json"
    config.write_text(json.dumps(profile.to_dict()), encoding="utf-8")
    source = tmp_path / "in.txt"
    source.write_text("a@example.com" if fmt == "text" else '{"email":"a@example.com"}', encoding="utf-8")
    assert main([str(source), "--format", fmt, "--policy", str(config)]) == 0
    output = capsys.readouterr().out
    assert "a@example.com" not in output
    if fmt == "text":
        assert output.strip() == profile.process("a@example.com").text
    else:
        assert json.loads(output) == profile.process_json({"email": "a@example.com"}).data


def test_cli_structured_fields_and_no_silent_text_drop(tmp_path, capsys):
    profile = PolicyProfile({"strategy": "redact", "field_labels": {"/name": "PERSON"}})
    config = tmp_path / "policy.json"
    config.write_text(json.dumps(profile.to_dict()), encoding="utf-8")
    source = tmp_path / "input.json"
    source.write_text('{"name":"custom-name"}', encoding="utf-8")
    assert main([str(source), "--format", "json", "--policy", str(config)]) == 0
    assert json.loads(capsys.readouterr().out) == profile.process_json({"name": "custom-name"}).data
    assert main([str(source), "--policy", str(config)]) == 2
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("flags", [
    ["--mode", "STRICT"], ["-mSTRICT"], ["--strategy=tokenize"], ["--include", "EMAIL"],
    ["--exclude", "PERSON"], ["--strategy-for", "EMAIL=redact"], ["--field-label", "/x=PERSON"],
    ["--person-exclusions-file", "x"], ["--field-person-exclusions", "x"], ["--field-rules", "x"],
    ["--batch"], ["--merge-mode", "union"], ["--with-privacy-filter"], ["--privacy-filter-device", "cpu"],
])
def test_cli_rejects_conflicting_flags(flags):
    with pytest.raises(SystemExit) as exc:
        main(["missing", "--policy", "policy.json", *flags])
    assert exc.value.code == 2


def test_policy_file_cannot_be_output_or_hardlink(tmp_path):
    config = tmp_path / "policy.json"
    config.write_text("{}", encoding="utf-8")
    link = tmp_path / "link"
    link.hardlink_to(config)
    for output in (config, link):
        with pytest.raises(SystemExit):
            main(["missing", "--policy", str(config), "--output", str(output)])
    assert config.read_text() == "{}"
