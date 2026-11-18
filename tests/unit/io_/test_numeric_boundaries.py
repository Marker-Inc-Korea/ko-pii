"""File preprocessing must not undo financial detector boundary checks."""
import pytest

from ko_pii import Anonymizer, detect_all
from ko_pii.io_ import read_text
from ko_pii.io_.bounded import read_text_bounded
from ko_pii.io_.isolated import read_text_isolated
from ko_pii.io_.text_normalizer import normalize_for_detection


@pytest.mark.parametrize("text", [
    "Account: 110-123-456789 100000",
    "Account: 110-123-456789\n100000",
    "Account: 110-123-456789\t100000",
    "Business: 123\n45\n67891",
    "Business: 123\r\n45\r\n67891",
    "Card: 3782-\n822463-\n10005",
])
def test_default_normalization_keeps_numeric_field_boundaries(text):
    normalized, offsets = normalize_for_detection(text)
    assert normalized == text
    assert offsets == list(range(len(text)))


@pytest.mark.parametrize("reader", [read_text, read_text_bounded, read_text_isolated])
def test_file_readers_do_not_merge_accounts_with_amounts_or_business_rows(tmp_path, reader):
    source = "계좌번호: 110-123-456789 100000\n사업자등록번호: 123\n45\n67891"
    path = tmp_path / "input.txt"
    path.write_bytes(source.encode("utf-8"))
    result = reader(str(path))
    text = result if isinstance(result, str) else result.text
    assert text == source
    masked = Anonymizer(strategy="redact", include=["ACCOUNT", "BUSINESS_REG"]).process(text)
    assert masked.text == "계좌번호: [계좌번호] 100000\n사업자등록번호: 123\n45\n67891"


@pytest.mark.parametrize("value", [
    "8 8 0 1 0 1 - 1 2 3 4 5 6 8",
    "88 0 1 0 1 - 1 2 3 4 5 6 8",
    "880101 - 1234568",
    "880101-\n1234568",
])
def test_supported_rrn_spacing_still_detects_and_remaps(value):
    text, offsets = normalize_for_detection(value)
    found = detect_all(text, include=["RRN"])
    assert len(found) == 1
    assert offsets[found[0].start] == 0
    assert offsets[found[0].end - 1] == len(value) - 1
    assert Anonymizer(strategy="redact", include=["RRN"]).process(text).text == "[주민등록번호]"


def test_aggressive_line_joining_remains_explicit_opt_in():
    source = "123\n45\n67891"
    assert normalize_for_detection(source)[0] == source
    assert normalize_for_detection(source, aggressive=True)[0] == "123 45 67891"


def test_korean_field_lines_are_not_concatenated_without_explicit_opt_in():
    source = "성명: 김다은\n성명: 김태성"
    normalized, offsets = normalize_for_detection(source)
    assert normalized == source
    assert offsets == list(range(len(source)))
    assert normalize_for_detection(source, aggressive=True)[0] == source.replace("\n", "")
