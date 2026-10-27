"""Text after HWPX inline controls must reach detection, not disappear."""
import json
from pathlib import Path
import zipfile

import pytest

from ko_pii import Anonymizer
from ko_pii.batch import process_paths
from ko_pii.cli import main
from ko_pii.io_ import read_text, read_text_bounded, read_text_isolated
from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy
from ko_pii.io_.hwpx import _extract_text_from_section, inspect_text
from ko_pii.io_.text_normalizer import normalize_for_detection
from ko_pii.vault import ReversibleVault


PARAGRAPH_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SECTION_NS = "http://www.hancom.co.kr/hwpml/2011/section"
CONTROLS = [("tab", "\t"), ("lineBreak", "\n"), ("nbSpace", "\u00a0"),
            ("fwSpace", "\u3000"), ("hyphen", "\u00ad")]
MARKS = ["markpenBegin", "markpenEnd", "titleMark", "insertBegin", "insertEnd",
         "deleteBegin", "deleteEnd"]
EMAILS = ["first@example.com", "second@example.com"]


def section(body):
    return (f'<hs:sec xmlns:hs="{SECTION_NS}" xmlns:hp="{PARAGRAPH_NS}">'
            f'{body}</hs:sec>').encode()


def paragraph(text):
    return f'<hp:p id="0"><hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>'


def package(path, body, *, later=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/hwp+zip")
        archive.writestr("Contents/section0.xml", section(body))
        if later is not None:
            archive.writestr("Contents/section1.xml", later)


@pytest.mark.parametrize("control,character", CONTROLS)
@pytest.mark.parametrize("prefix", ["", "label:"])
def test_inline_control_preserves_following_text(control, character, prefix):
    text = paragraph(f'{prefix}<hp:{control}/>{EMAILS[0]}')
    assert "".join(_extract_text_from_section(section(text))) == f'\n{prefix}{character}{EMAILS[0]}'


@pytest.mark.parametrize("mark", MARKS)
@pytest.mark.parametrize("prefix", ["", "first"])
def test_nonprinting_marks_do_not_drop_or_separate_text(mark, prefix):
    body = paragraph(f'{prefix}<hp:{mark} id="1"/>@example.com')
    assert "".join(_extract_text_from_section(section(body))) == f'\n{prefix}@example.com'


def test_mixed_controls_preserve_order_and_exactly_once():
    body = paragraph('A<hp:tab/>B<hp:lineBreak/>C<hp:markpenBegin color="#000000"/>'
                     'D<hp:markpenEnd/>E<hp:nbSpace/>F<hp:fwSpace/>G<hp:hyphen/>H')
    assert "".join(_extract_text_from_section(section(body))) == '\nA\tB\nCDE\u00a0F\u3000G\u00adH'


def test_plain_runs_and_paragraph_separators_remain_compatible():
    body = '<hp:p><hp:run><hp:t>one</hp:t></hp:run><hp:run><hp:t>two</hp:t></hp:run>' \
           '<hp:linesegarray/></hp:p>' + paragraph('three')
    assert "".join(_extract_text_from_section(section(body))) == '\nonetwo\n\nthree'


def test_text_scope_does_not_capture_xml_layout_or_attributes():
    body = '<hp:p attr="attribute-secret">\n  <hp:run>outside-before<hp:t>A<hp:tab/>' \
           'B</hp:t>outside-after</hp:run>\n</hp:p>'
    assert "".join(_extract_text_from_section(section(body))) == '\nA\tB'


def test_empty_text_and_nested_text_do_not_duplicate_values():
    # Nested text is a defensive parser case, not a claim of schema validity.
    body = paragraph('<hp:t>A<hp:tab/>B</hp:t>C') + paragraph('')
    assert "".join(_extract_text_from_section(section(body))) == '\nA\tBC\n'


def test_deep_structure_does_not_introduce_python_recursion_limit():
    depth = 1500
    body = '<hp:subList>' * depth + paragraph('<hp:tab/>' + EMAILS[0]) + '</hp:subList>' * depth
    assert "".join(_extract_text_from_section(section(body))) == '\n\t' + EMAILS[0]


@pytest.mark.parametrize("reader", [read_text, read_text_bounded, read_text_isolated])
def test_all_text_readers_preserve_inline_content(tmp_path, reader):
    path = tmp_path / "contacts.hwpx"
    package(path, paragraph(f'email:<hp:tab/>{EMAILS[0]}<hp:lineBreak/>{EMAILS[1]}'))
    result = reader(str(path))
    actual = result if isinstance(result, str) else result.text
    expected, _ = normalize_for_detection(f'\nemail:\t{EMAILS[0]}\n{EMAILS[1]}')
    assert actual == expected
    masked = Anonymizer(include=["EMAIL"]).process(actual)
    assert [d.detection.text for d in masked.detections] == EMAILS
    for email in EMAILS:
        assert email not in masked.text
    assert masked.vault.reveal("<EMAIL_1>") == EMAILS[0]
    assert masked.vault.reveal("<EMAIL_2>") == EMAILS[1]


def test_nested_table_and_header_text_reaches_inspection_once(tmp_path):
    path = tmp_path / "nested.hwpx"
    body = '<hp:p><hp:run><hp:ctrl><hp:header><hp:subList>' + paragraph('<hp:tab/>' + EMAILS[0]) \
           + '</hp:subList></hp:header></hp:ctrl><hp:tbl><hp:tr><hp:tc><hp:subList>' \
           + paragraph('<hp:lineBreak/>' + EMAILS[1]) + '</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>'
    package(path, body)
    result = inspect_text(str(path))
    assert result.coverage["status"] == "complete"
    assert result.parts[0]["status"] == "read"
    assert all(result.text.count(value) == 1 for value in EMAILS)


def test_cli_masks_and_restores_text_after_controls(tmp_path, capsys):
    path = tmp_path / "contacts.hwpx"
    output = tmp_path / "contacts.txt"
    vault_path = tmp_path / "vault.json"
    package(path, paragraph(f'email:<hp:tab/>{EMAILS[0]}<hp:lineBreak/>{EMAILS[1]}'))
    assert main([str(path), "--include", "EMAIL", "--output", str(output),
                 "--vault", str(vault_path), "--json-summary"]) == 0
    captured = capsys.readouterr()
    assert isinstance(json.loads(captured.err), dict)
    assert output.read_text(encoding="utf-8").count("<EMAIL_") == 2
    vault = ReversibleVault.load(str(vault_path))
    assert vault.reveal("<EMAIL_1>") == EMAILS[0]
    assert vault.reveal("<EMAIL_2>") == EMAILS[1]
    assert all(value not in captured.err for value in EMAILS)


def test_batch_keeps_content_instead_of_succeeding_on_prefix_only(tmp_path):
    path = tmp_path / "contacts.hwpx"
    package(path, paragraph('email:<hp:tab/>' + EMAILS[0]))
    result = process_paths([str(path)], str(tmp_path / "out"), include=["EMAIL"], progress=False)
    assert result.succeeded == 1 and result.failed == 0
    assert "<EMAIL_1>" in Path(result.results[0].output_path).read_text(encoding="utf-8")


def test_later_parse_failure_still_prevents_partial_publication(tmp_path, capsys):
    path = tmp_path / "partial.hwpx"
    output = tmp_path / "previous.txt"
    output.write_text("previous", encoding="utf-8")
    vault = tmp_path / "vault.json"
    package(path, paragraph('email:<hp:tab/>' + EMAILS[0]), later=b'<broken>')
    assert main([str(path), "--output", str(output), "--vault", str(vault), "--json-summary"]) == 1
    report = json.loads(capsys.readouterr().err)
    assert report["error"] == "document_extraction_incomplete"
    assert report["extraction_coverage"]["status"] == "partial"
    assert output.read_text(encoding="utf-8") == "previous"
    assert not vault.exists()


@pytest.mark.parametrize("mark", MARKS)
def test_email_split_by_nonprinting_mark_is_detected_and_restorable(tmp_path, mark):
    path = tmp_path / "marked.hwpx"
    package(path, paragraph(f'first<hp:{mark} id="1"/>@example.com'))
    result = Anonymizer(include=["EMAIL"]).process(read_text(str(path)))
    assert result.text == '\n<EMAIL_1>'
    assert result.vault.reveal("<EMAIL_1>") == EMAILS[0]


def test_restored_tail_counts_towards_text_limit(tmp_path):
    path = tmp_path / "limited.hwpx"
    package(path, paragraph('email:<hp:tab/>' + EMAILS[0]))
    with pytest.raises(BoundedReadError) as error:
        read_text_bounded(path, policy=FileReadPolicy(max_text_chars=12))
    assert error.value.code == "extracted_text_too_large"
