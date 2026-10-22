import json

import pytest

from ko_pii import Anonymizer, EACH, FieldRule, ProcessingMode, RegexDetector, anonymize_json, anonymize_jsonl
from ko_pii.cli import main


def test_exclusion_is_field_scoped_and_never_changes_shared_configuration():
    anon = Anonymizer(strategy="redact", include=["PERSON"],
                      secondary_detector=RegexDetector("홍길동", label="PERSON"))
    data = {"product": "홍길동", "customer": "홍길동", "other": ["홍길동"]}
    result = anonymize_json(data, anonymizer=anon, field_person_exclusions={"/product": ["홍길동"]})
    assert result.data == {"product": "홍길동", "customer": "[성명]", "other": ["[성명]"]}
    assert data["customer"] == "홍길동"
    assert anon.person_exclusions == frozenset()
    assert anon.process("홍길동").text == "[성명]"
    assert "홍길동" not in json.dumps(result.report(), ensure_ascii=False)


@pytest.mark.parametrize("assertion", ["pointer", "rule"])
@pytest.mark.parametrize("mode", [ProcessingMode.STRICT, ProcessingMode.AUDIT])
def test_asserted_field_wins_over_global_and_local_exclusions(assertion, mode):
    kw = ({"field_labels": {"/names/0": "PERSON"}} if assertion == "pointer" else
          {"field_rules": [FieldRule(("names", EACH), "PERSON")]})
    result = anonymize_json({"names": ["홍길동"]},
                            anonymizer=Anonymizer(mode=mode, person_exclusions=["홍길동"]),
                            field_person_exclusions={"/names/0": ["홍길동"]}, **kw)
    assert result.data["names"] == (["홍길동"] if mode == ProcessingMode.AUDIT else ["<PERSON_1>"])


def test_only_person_and_exact_normalized_value_are_suppressed():
    anon = Anonymizer(strategy="redact", include=["EMAIL", "PERSON"],
                      secondary_detector=RegexDetector("홍길동", label="PERSON"))
    result = anonymize_json({"field": "홍길동 user@example.com"}, anonymizer=anon,
                            field_person_exclusions={"/field": ["홍\u200b길동", "user@example.com"]})
    assert result.data == {"field": "홍길동 [이메일]"}
    result = anonymize_json({"field": "홍길동"}, anonymizer=anon,
                            field_person_exclusions={"/field": ["홍길"]})
    assert result.data["field"] == "[성명]"


def test_escaped_keys_root_null_and_array_index():
    data = {"a/b": {"~": ["홍길동", None]}}
    result = anonymize_json(data, field_person_exclusions={"/a~1b/~0/0": ["홍길동"], "/a~1b/~0/1": []})
    assert result.data == data
    assert anonymize_json("홍길동", field_person_exclusions={"": ["홍길동"]}).data == "홍길동"


@pytest.mark.parametrize("config", [
    [], {"bad": []}, {"/a~2b": []}, {"/missing": []}, {"/arr/01": []},
    {"/arr/0": "홍길동"}, {"/arr/0": [1]}, {"/arr/0": None}, {"/arr/0": [""]},
    {"/arr": []}, {"/number": []}, {"/arr/0": ["x"] * 257}, {"/arr/0": ["x" * 257]},
    {"/arr/999999999999999999999999": []},
    {"/arr/0": ["\u200b"]}, {"/arr/0": ["\ufdfa" * 100]},
])
def test_invalid_configs_fail_before_vault_mutation(config):
    anon = Anonymizer()
    with pytest.raises(ValueError):
        anonymize_json({"first": "user@example.com", "arr": ["홍길동"], "number": 123},
                       anonymizer=anon, field_person_exclusions=config)
    assert len(anon.vault) == 0


def test_jsonl_prevalidates_all_paths_and_materializes_term_generator_once():
    anon = Anonymizer()
    with pytest.raises(ValueError, match="line 2"):
        anonymize_jsonl('{"name":"홍길동"}\n{"missing":"user@example.com"}', anonymizer=anon,
                        field_person_exclusions={"/name": iter(["홍길동"])})
    assert len(anon.vault) == 0
    results = anonymize_jsonl('{"name":"홍길동"}\n{"name":"홍길동"}',
                             field_person_exclusions={"/name": iter(["홍길동"])})
    assert [r.data for r in results] == [{"name": "홍길동"}] * 2


@pytest.mark.parametrize("format", ["json", "jsonl"])
def test_cli_field_exclusions_and_explanation(tmp_path, format):
    source, config, output, report = [tmp_path / n for n in ("in.json", "policy.json", "out.json", "report.json")]
    source.write_text(json.dumps({"term": "홍길동", "name": "홍길동", "mail": "user@example.com"}), encoding="utf-8")
    config.write_text(json.dumps({"/term": ["홍길동"]}), encoding="utf-8")
    assert main([str(source), "--format", format, "--strategy", "redact",
                 "--field-person-exclusions", str(config), "--field-label", "/name=PERSON",
                 "-o", str(output), "--explain", str(report), "--trace-limit", "5"]) == 0
    assert json.loads(output.read_text()) == {"term": "홍길동", "name": "[성명]", "mail": "[이메일]"}
    assert "홍길동" not in report.read_text(encoding="utf-8")
    assert "overlap_trace" in report.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        main([str(source), "--format", format, "--field-person-exclusions", str(config), "-o", str(config)])


def test_cli_rejects_field_configuration_in_text_mode(tmp_path):
    with pytest.raises(SystemExit):
        main(["-", "--field-person-exclusions", str(tmp_path / "unused.json")])


@pytest.mark.parametrize("config", ["null", "[]", '{"/term":"secret-source-term"}'])
def test_cli_bad_policy_does_not_write_output_or_reflect_values(tmp_path, capsys, config):
    source, policy, output = [tmp_path / n for n in ("input.json", "policy.json", "output.json")]
    source.write_text('{"term":"user@example.com"}', encoding="utf-8")
    policy.write_text(config, encoding="utf-8")
    assert main([str(source), "--format", "json", "--field-person-exclusions", str(policy), "-o", str(output)]) != 0
    assert not output.exists()
    assert "secret-source-term" not in capsys.readouterr().err
