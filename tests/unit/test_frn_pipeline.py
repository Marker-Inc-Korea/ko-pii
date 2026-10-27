"""Legacy foreign-registration arithmetic must not reuse the resident digit.

Synthetic values only. The complement-weight oracle follows the checksum
portion of eGovFrame EgovNumberCheckUtil, revision f13bf51f44c6a11b968995768e94fa1d994c8c0a.
It is not an identity, issuance, or real-document validation oracle.
"""
from datetime import date

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json
from ko_pii.cli import main
from ko_pii.patterns import corp_reg, frn
from ko_pii.tabular import anonymize_records


VALUES = ["850315-5245676", "850315-6000000", "000101-7000001", "000101-8000003"]


def _legacy_digit(prefix):
    remainder = sum(int(digit) * (9 - i % 8) for i, digit in enumerate(prefix)) % 11
    return ({0: 1, 10: 0}.get(remainder, remainder) + 2) % 10


@pytest.mark.parametrize("value", VALUES)
def test_foreign_not_resident_arithmetic_sets_confidence(value):
    digits = value.replace("-", "")
    assert _legacy_digit(digits[:12]) == int(digits[12])
    detection, = frn.detect(value)
    assert detection.confidence == 1.0
    assert detection.extra["checksum_valid"] is True
    assert "checksum:valid" in detection.evidence


@pytest.mark.parametrize("value", VALUES)
def test_resident_only_check_digit_is_not_high_confidence_foreign_number(value):
    wrong = value[:-1] + str((int(value[-1]) - 2) % 10)
    detection, = frn.detect(wrong)
    assert detection.confidence == 0.7
    assert detection.extra["checksum_valid"] is False
    result = Anonymizer(mode=ProcessingMode.BALANCED, include=["FRN"], strategy="redact").process(wrong)
    assert result.text == wrong


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("mode", [ProcessingMode.PARANOID, ProcessingMode.STRICT,
                                  ProcessingMode.BALANCED, ProcessingMode.PERMISSIVE])
def test_legacy_frn_is_replaced_in_every_blocking_mode(value, mode):
    source = "\uc678\uad6d\uc778\ub4f1\ub85d\ubc88\ud638: " + value
    result = Anonymizer(mode=mode, include=["FRN"], strategy="redact").process(source)
    assert value not in result.text
    assert result.text.endswith("[\uc678\uad6d\uc778\ub4f1\ub85d\ubc88\ud638]")
    assert result.detections[0].detection.text == value


@pytest.mark.parametrize("value", VALUES)
@pytest.mark.parametrize("entry", ["text", "json", "table"])
def test_fpe_uses_foreign_check_digit_and_keeps_original_in_vault(value, entry):
    vault = ReversibleVault(salt="synthetic-frn-regression")
    anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="fpe", vault=vault, include=["FRN"])
    if entry == "json":
        output = anonymize_json({"id": value}, anonymizer=anon, field_labels={"/id": "FRN"}).data["id"]
    elif entry == "table":
        rows, _ = anonymize_records([{"id": value}], column_map={"id": "FRN"},
                                    strategy="fpe", vault=vault)
        output = rows[0]["id"]
    else:
        output = anon.process(value).text
    digits = output.replace("-", "")
    assert len(output) == 14 and output[6] == "-" and len(digits) == 13 and digits.isascii() and digits.isdigit()
    assert output != value and output[7] == value[7]
    assert int(digits[-1]) == _legacy_digit(digits[:12])
    assert vault.reveal("<FRN_1>") == value


@pytest.mark.parametrize("value", ["8503155000993", "8503156000083", "0503157000353", "0503158000021"])
def test_corporate_checksum_collision_retains_foreign_identity(value):
    from ko_pii.checksum.corp_reg_checksum import is_valid_checksum
    assert is_valid_checksum(value)
    assert _legacy_digit(value[:12]) == int(value[-1])
    assert list(corp_reg.detect(value)) == []
    detection, = frn.detect(value)
    assert detection.confidence == 1.0
    result = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact").process(value)
    assert result.text == "[\uc678\uad6d\uc778\ub4f1\ub85d\ubc88\ud638]"


@pytest.mark.parametrize("separator", ["", "-", " / ", "-\n"])
def test_normalized_and_wrapped_frn_is_replaced_without_changing_neighbors(separator):
    source_value = "850315" + separator + "5245676"
    noisy = source_value.translate(str.maketrans("0123456789", "\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19"))
    source = "ID: " + noisy + " end"
    result = Anonymizer(mode=ProcessingMode.BALANCED, include=["FRN"], strategy="redact").process(source)
    assert result.text == "ID: [\uc678\uad6d\uc778\ub4f1\ub85d\ubc88\ud638] end"
    assert result.detections[0].detection.text == noisy


def test_checksum_failure_is_unverified_not_proof_of_invalid_identity():
    source = "850315-5245679"
    detection, = frn.detect(source)
    assert detection.confidence == 0.7 and detection.extra["checksum_valid"] is False
    assert "checksum:unverified" in detection.evidence
    assert Anonymizer(mode=ProcessingMode.STRICT, include=["FRN"], strategy="redact").process(source).text != source


def test_audit_and_explicit_assertion_keep_their_policy():
    source = "850315-5245679"
    audit = Anonymizer(mode=ProcessingMode.AUDIT, include=["FRN"])
    assert audit.process(source).text == source and len(audit.vault) == 0
    anon = Anonymizer(mode=ProcessingMode.BALANCED, strategy="redact", include=["FRN"])
    assert anonymize_json({"id": source}, anonymizer=anon, field_labels={"/id": "FRN"}).data["id"] != source


def test_future_birth_is_not_emitted_but_today_and_past_century_are(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 27)

    monkeypatch.setattr(frn, "date", FixedDate)
    for front, gender, present in [("261028", "7", False), ("261027", "7", True), ("261028", "5", True)]:
        prefix = front + gender + "00000"
        source = prefix + str(_legacy_digit(prefix))
        assert bool(list(frn.detect(source))) is present


@pytest.mark.parametrize("value", ["0002295000035", "2610287000373", "0002291000261", "2610283000781"])
def test_corporate_candidate_not_lost_to_impossible_personal_birth(value, monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 27)

    monkeypatch.setattr(corp_reg, "date", FixedDate)
    detection, = corp_reg.detect(value)
    assert detection.label == "CORP_REG"


def test_cli_balanced_masks_the_legacy_foreign_number(tmp_path):
    source, output = tmp_path / "input.txt", tmp_path / "output.txt"
    source.write_text(VALUES[0], encoding="utf-8")
    assert main([str(source), "--mode", "BALANCED", "--include", "FRN",
                 "--strategy", "redact", "--output", str(output)]) == 0
    assert output.read_text(encoding="utf-8") == "[\uc678\uad6d\uc778\ub4f1\ub85d\ubc88\ud638]"
