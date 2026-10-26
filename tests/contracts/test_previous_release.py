"""Read artifacts produced by the published package, not rebuilt fixtures."""
import inspect
from enum import Enum
import json
from pathlib import Path

import ko_pii
from ko_pii.cli import main
from ko_pii.reporting import explain


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/1.22.0.json").read_text(encoding="utf-8")
)


def test_previous_exports_and_call_shapes():
    assert set(FIXTURE["exports"]) <= set(ko_pii.__all__)
    for name, previous in FIXTURE["signatures"].items():
        target = getattr(ko_pii, name)
        # EnumMeta signatures vary across Python versions; check values below.
        if isinstance(target, type) and issubclass(target, Enum):
            continue
        current = inspect.signature(target).parameters
        old_names = {p["name"] for p in previous}
        for parameter in previous:
            new = current[parameter["name"]]
            assert new.kind.name == parameter["kind"], name
            if not parameter["required"]:
                assert new.default is not inspect.Parameter.empty or new.kind in (
                    new.VAR_POSITIONAL, new.VAR_KEYWORD,
                ), name
        old_positional = [p["name"] for p in previous if p["kind"] in (
            "POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD",
        )]
        new_positional = [p.name for p in current.values() if p.kind in (
            p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD,
        )]
        assert new_positional[:len(old_positional)] == old_positional, name
        for new in current.values():
            if new.name not in old_names:
                assert new.default is not inspect.Parameter.empty or new.kind in (
                    new.VAR_POSITIONAL, new.VAR_KEYWORD,
                ), name


def test_previous_enum_values():
    for name, members in FIXTURE["enums"].items():
        target = getattr(ko_pii, name)
        for key, value in members.items():
            assert target[key].value == value
            assert target(value) is target[key]


def test_previous_vault_roundtrip_and_next_token():
    vault = ko_pii.ReversibleVault.loads(json.dumps(FIXTURE["vault"]))
    assert vault.reveal("<EMAIL_1>") == "demo@example.com"
    assert vault.store("EMAIL", "demo@example.com", 3) == "<EMAIL_1>"
    assert vault.store("EMAIL", "next@example.com", 3) == "<EMAIL_2>"
    restored = ko_pii.ReversibleVault.loads(vault.dumps())
    assert restored.reveal("<EMAIL_2>") == "next@example.com"
    assert restored.to_dict()["schema_version"] == FIXTURE["vault"]["schema_version"]


def _assert_subset(expected, actual):
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            _assert_subset(value, actual[key])
    elif isinstance(expected, list):
        assert len(expected) == len(actual)
        for left, right in zip(expected, actual):
            _assert_subset(left, right)
    else:
        assert expected == actual


def test_previous_profile_and_explanation_semantics():
    profile = ko_pii.PolicyProfile.from_dict(FIXTURE["profile"])
    assert profile.fingerprint == FIXTURE["profile_fingerprint"]
    result = profile.process("demo@example.com")
    assert result.text == "<EMAIL_1>"
    _assert_subset(FIXTURE["explanation"], explain(result))


def test_previous_profile_cli(tmp_path):
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(FIXTURE["profile"]), encoding="utf-8")
    source = tmp_path / "input.txt"
    source.write_text("demo@example.com", encoding="utf-8")
    output = tmp_path / "output.txt"
    report = tmp_path / "report.json"
    assert main([str(source), "--policy", str(policy), "-o", str(output),
                 "--explain", str(report)]) == 0
    assert output.read_text(encoding="utf-8") == "<EMAIL_1>"
    _assert_subset(FIXTURE["explanation"], json.loads(report.read_text(encoding="utf-8")))
