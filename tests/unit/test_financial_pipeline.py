"""Financial format regressions through public detection and transformation APIs."""
import pytest

from ko_pii import Anonymizer, ProcessingMode, anonymize_json, detect_all
from ko_pii.cli import main
from ko_pii.vault.reversible import ReversibleVault


CASES = [
    ("ACCOUNT", "계좌번호: ", "110-123-456789", " 100000", "[계좌번호]"),
    ("ACCOUNT", "신한은행 ", "110123456789", "\n1234", "[계좌번호]"),
    ("CARD", "Card: ", "3782 822463 10005", " [end]", "[카드번호]"),
    ("CARD", "Card: ", "3056-930902-5904", " [end]", "[카드번호]"),
    ("CARD", "Card: ", "4000 0000 0000 0000 006", " [end]", "[카드번호]"),
    ("BUSINESS_REG", "사업자등록번호: ", "123 45 67891", " [end]", "[사업자등록번호]"),
    ("BUSINESS_REG", "사업자등록번호: ", "123 . 45 . 67891", " [end]", "[사업자등록번호]"),
]


def _variant(value, form):
    if form == "fullwidth":
        return "".join(chr(ord(ch) + 0xFEE0) if "!" <= ch <= "~" else ch for ch in value)
    if form == "invisible":
        return value[:2] + "\u200b" + value[2:]
    return value


@pytest.mark.parametrize("label,prefix,value,suffix,replacement", CASES)
@pytest.mark.parametrize("form", ["ascii", "fullwidth", "invisible"])
def test_detection_and_redaction_preserve_source_coordinates(label, prefix, value, suffix, replacement, form):
    raw = _variant(value, form)
    prefix = "\ufb01 " + prefix
    source = prefix + raw + suffix
    found = detect_all(source, include=[label])
    assert len(found) == 1
    detection = found[0]
    assert (detection.start, detection.end, detection.text) == (len(prefix), len(prefix) + len(raw), raw)
    assert detection.rule_id == "ko-pii." + label.lower() + ".v1"
    result = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact", include=[label]).process(source)
    assert result.text == prefix + replacement + suffix


@pytest.mark.parametrize("label,prefix,value,suffix,replacement", CASES)
@pytest.mark.parametrize("form", ["ascii", "fullwidth", "invisible"])
def test_tokenization_restores_the_exact_original_not_neighboring_fields(label, prefix, value, suffix, replacement, form):
    raw = _variant(value, form)
    vault = ReversibleVault(salt="financial", secret_key="test", fingerprint_iterations=1)
    engine = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize", include=[label], vault=vault)
    token = "<" + label + "_1>"
    first = engine.process(prefix + raw + suffix)
    second = engine.process(prefix + raw + suffix)
    assert first.text == second.text == prefix + token + suffix
    assert vault.reveal(token) == raw
    assert len(vault.entries()) == 1


@pytest.mark.parametrize("label,prefix,value,suffix,replacement", CASES)
def test_structured_text_uses_the_same_detector(label, prefix, value, suffix, replacement):
    source = {"note": prefix + value + suffix, "amount": 100000}
    engine = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact", include=[label])
    result = anonymize_json(source, anonymizer=engine)
    assert result.data == {"note": prefix + replacement + suffix, "amount": 100000}
    assert source["note"] == prefix + value + suffix


@pytest.mark.parametrize("label,prefix,value,suffix,replacement", CASES)
def test_cli_tokenization_and_persisted_vault(tmp_path, label, prefix, value, suffix, replacement):
    source, output, vault_path = (tmp_path / name for name in ("input.txt", "output.txt", "vault.json"))
    source.write_text(prefix + value + suffix, encoding="utf-8")
    assert main([str(source), "--include", label, "--strategy", "tokenize",
                 "--output", str(output), "--vault", str(vault_path)]) == 0
    token = "<" + label + "_1>"
    assert output.read_text(encoding="utf-8") == prefix + token + suffix
    vault = ReversibleVault.load(vault_path)
    assert vault.reveal(token) == value


def test_default_label_selection_masks_all_three_without_consuming_the_amount():
    source = (
        "계좌번호: 110-123-456789 100000\n"
        "카드번호: 3782 822463 10005\n"
        "사업자등록번호: 123 45 67891"
    )
    result = Anonymizer(strategy="redact").process(source)
    assert result.text == "계좌번호: [계좌번호] 100000\n카드번호: [카드번호]\n사업자등록번호: [사업자등록번호]"
