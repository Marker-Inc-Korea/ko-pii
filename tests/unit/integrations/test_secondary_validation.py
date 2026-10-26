from dataclasses import replace

import pytest

from ko_pii import Anonymizer, DetectionResult, ProcessingMode, ReversibleVault, RiskLevel
from ko_pii.integrations.hybrid import MergeMode, merge_detections


class DirectAdapter:
    def __init__(self, callback):
        self.callback = callback

    def detect(self, text):
        return self.callback(text)


GOOD = DetectionResult("ACCOUNT", "abc", 0, 3, RiskLevel.HIGH)


@pytest.mark.parametrize("bad", [
    None, "abc", replace(GOOD, label="UNKNOWN"), replace(GOOD, text="xyz"),
    replace(GOOD, start=-1), replace(GOOD, start=True), replace(GOOD, end=0),
    replace(GOOD, end=4), replace(GOOD, end=3.0), replace(GOOD, risk_level=4),
    replace(GOOD, confidence=float("nan")), replace(GOOD, confidence=float("inf")),
    replace(GOOD, confidence=-0.1), replace(GOOD, confidence=1.1), replace(GOOD, confidence=True),
    replace(GOOD, evidence="private"), replace(GOOD, extra=[]), replace(GOOD, normalized="private"),
    replace(GOOD, rule_id=[]), replace(GOOD, legal_basis=123), replace(GOOD, subrule_id=[]),
])
def test_direct_adapter_rejects_malformed_later_result_without_vault_writes(bad):
    vault = ReversibleVault()
    vault.store(label="ACCOUNT", original="existing", risk_level=4)
    before = vault.dumps()
    anon = Anonymizer(vault=vault, secondary_detector=DirectAdapter(lambda text: [GOOD, bad]))
    with pytest.raises(ValueError, match="secondary detector"):
        anon.process("abc")
    assert vault.dumps() == before


@pytest.mark.parametrize("mode", list(MergeMode))
@pytest.mark.parametrize("processing_mode", list(ProcessingMode))
def test_validation_before_filters_merge_and_audit(mode, processing_mode):
    # ACCOUNT would be filtered out, but an invalid adapter is never a silent success.
    bad = replace(GOOD, text="DO_NOT_LOG_THIS")
    anon = Anonymizer(include=["EMAIL"], mode=processing_mode, merge_mode=mode,
                      secondary_detector=DirectAdapter(lambda text: [bad]))
    with pytest.raises(ValueError) as error:
        anon.process("abc")
    assert "DO_NOT_LOG_THIS" not in str(error.value)
    assert len(anon.vault) == 0


def test_generator_failure_is_sanitized_before_primary_or_secondary_storage():
    def fail(text):
        yield DetectionResult("ACCOUNT", text, 0, len(text), RiskLevel.HIGH)
        raise RuntimeError(text)
    anon = Anonymizer(secondary_detector=DirectAdapter(fail))
    with pytest.raises(ValueError) as error:
        anon.process("user@example.com")
    assert "user@example.com" not in str(error.value)
    assert len(anon.vault) == 0


def test_reused_mutable_records_are_snapshotted_with_metadata():
    record = replace(GOOD, evidence=["source:local"], extra={"source": "local"},
                     rule_id="local.rule.v1", subrule_id="local.subrule.v1")
    def reused(text):
        yield record
        record.text, record.start, record.end = "def", 4, 7
        record.evidence.append("second")
        record.extra["source"] = "second"
        yield record
        record.text = "corrupted-after-yield"
    result = Anonymizer(include=["ACCOUNT"], secondary_detector=DirectAdapter(reused)).process("abc def")
    assert result.text == "<ACCOUNT_1> <ACCOUNT_2>"
    assert result.vault.reveal("<ACCOUNT_1>") == "abc"
    assert result.vault.reveal("<ACCOUNT_2>") == "def"
    first, second = [r.detection for r in result.detections]
    assert first.evidence == ["source:local"]
    assert first.extra == {"source": "local"}
    assert second.extra == {"source": "second"}
    assert first.rule_id == "local.rule.v1" and first.subrule_id == "local.subrule.v1"


@pytest.mark.parametrize("settings", [
    {"merge_mode": "typo"}, {"merge_mode": None}, {"merge_mode": []},
    {"role_split_labels": ["PESRON"]}, {"role_split_labels": "PERSON"},
    {"role_split_labels": [True]}, {"role_split_labels": 123},
    {"secondary_detector": object()},
])
def test_constructor_rejects_bad_configuration_without_calling_detector(settings):
    def unexpected(text):
        pytest.fail("configuration error must precede detector invocation")
    with pytest.raises(ValueError):
        Anonymizer(**{"secondary_detector": DirectAdapter(unexpected), **settings})


@pytest.mark.parametrize("mode,labels", [("typo", None), ("union", ["PESRON"]), ("role_split", "PERSON")])
def test_low_level_merge_rejects_bad_configuration_before_consuming_inputs(mode, labels):
    def unexpected():
        pytest.fail("bad merge settings must not consume input")
        yield GOOD
    with pytest.raises(ValueError):
        merge_detections(unexpected(), unexpected(), mode=mode, role_split_labels=labels)


def test_role_split_valid_empty_and_generator_semantics_are_preserved():
    adapter = DirectAdapter(lambda text: [replace(GOOD, label="PERSON")])
    anon = Anonymizer(secondary_detector=adapter, merge_mode="role_split",
                      role_split_labels=iter(["PERSON", "PERSON"]))
    assert anon.role_split_labels == frozenset(["PERSON"])
    assert anon.process("abc").text == "<PERSON_1>"
    assert anon.process("abc").text == "<PERSON_1>"
    empty = Anonymizer(secondary_detector=adapter, merge_mode="role_split", role_split_labels=[])
    assert empty.process("abc").text == "abc"


def test_mutated_merge_configuration_rechecked_before_detector_call():
    anon = Anonymizer(secondary_detector=DirectAdapter(lambda text: pytest.fail("must not invoke")))
    anon.role_split_labels = frozenset(["PESRON"])
    with pytest.raises(ValueError):
        anon.process("abc")
