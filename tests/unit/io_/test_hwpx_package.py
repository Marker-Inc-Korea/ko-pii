"""HWPX package order and declared body parts must not be guessed or lost."""
from pathlib import Path
import json
from xml.sax.saxutils import quoteattr
import zipfile

import pytest

from ko_pii import Anonymizer
from ko_pii.batch import process_paths
from ko_pii.cli import main
from ko_pii.io_ import read_text, read_text_bounded, read_text_isolated
from ko_pii.io_.bounded import BoundedReadError
from ko_pii.io_.coverage import DocumentExtractionError
from ko_pii.io_.hwpx import inspect_text
from ko_pii.vault import ReversibleVault


OPF = "http://www.idpf.org/2007/opf/"
SECTION = "http://www.hancom.co.kr/hwpml/2011/section"
PARAGRAPH = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HEAD = "http://www.hancom.co.kr/hwpml/2011/head"
MANIFEST = "Contents/content.hpf"


def body(text):
    return f'<sec xmlns="{SECTION}"><p xmlns="{PARAGRAPH}"><run><t>{text}</t></run></p></sec>'


def content(items, spine, *, metadata="", namespace=OPF):
    item_xml = ''.join(f'<item id={quoteattr(key)} href={quoteattr(path)} media-type="application/xml"/>'
                       for key, path in items)
    refs = ''.join(f'<itemref idref={quoteattr(key)}/>' for key in spine)
    return (f'<package xmlns="{namespace}"><metadata>{metadata}</metadata>'
            f'<manifest>{item_xml}</manifest><spine>{refs}</spine></package>')


def package(path, xml, parts):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('mimetype', 'application/hwp+zip')
        if xml is not None:
            archive.writestr(MANIFEST, xml)
        for name, text in parts.items():
            archive.writestr(name, text)


def check_failed(path):
    result = inspect_text(str(path))
    assert result.coverage['status'] in {'partial', 'failed'}
    with pytest.raises(DocumentExtractionError):
        result.require_complete()


@pytest.mark.parametrize('reader', [read_text, read_text_bounded, read_text_isolated])
def test_spine_not_filename_or_zip_order_controls_text_and_tokens(tmp_path, reader):
    path = tmp_path / 'ordered.hwpx'
    xml = content([('a', 'Contents/section0.xml'), ('b', 'Contents/section1.xml')], ['b', 'a'])
    package(path, xml, {'Contents/section0.xml': body('first@example.com'),
                       'Contents/section1.xml': body('second@example.com')})
    extracted = reader(str(path))
    text = extracted if isinstance(extracted, str) else extracted.text
    assert text.index('second@example.com') < text.index('first@example.com')
    result = Anonymizer(include=['EMAIL']).process(text)
    assert result.vault.reveal('<EMAIL_1>') == 'second@example.com'
    assert result.vault.reveal('<EMAIL_2>') == 'first@example.com'


@pytest.mark.parametrize('reader', [read_text, read_text_bounded, read_text_isolated])
@pytest.mark.parametrize('href', ['Contents/body.xml', 'body.xml', './body.xml', 'body%20one.xml'])
def test_manifest_can_name_a_body_without_section_filename(tmp_path, reader, href):
    path = tmp_path / 'renamed.hwpx'
    part = 'Contents/body one.xml' if '%20' in href else 'Contents/body.xml'
    package(path, content([('body', href)], ['body']), {part: body('first@example.com')})
    result = reader(str(path))
    text = result if isinstance(result, str) else result.text
    assert 'first@example.com' in text


@pytest.mark.parametrize('namespace', [OPF, OPF.rstrip('/')])
def test_metadata_and_header_are_read_without_reordering_body(tmp_path, namespace):
    path = tmp_path / 'metadata.hwpx'
    xml = content([('head', 'Contents/header.xml'), ('a', 'Contents/section0.xml')], ['head', 'a'],
                  metadata='<title>title@example.com</title><meta name="creator" content="text">'
                           'author@example.com</meta><meta name="creator" content="text">'
                           'other@example.com</meta><meta name="keyword" content="text">'
                           'keyword@example.com</meta>', namespace=namespace)
    package(path, xml, {'Contents/header.xml': f'<head xmlns="{HEAD}"/>',
                       'Contents/section0.xml': body('body@example.com')})
    result = inspect_text(str(path))
    assert result.coverage['status'] == 'complete'
    assert all(result.text.count(value + '@example.com') == 1
               for value in ['title', 'author', 'other', 'keyword', 'body'])
    assert [part['part'] for part in result.parts] == [MANIFEST, 'Contents/header.xml', 'Contents/section0.xml']


def test_prefixes_and_non_linear_sections_do_not_hide_text(tmp_path):
    path = tmp_path / 'prefixed.hwpx'
    xml = (f'<o:package xmlns:o="{OPF}"><o:manifest>'
           '<o:item id="a" href="Contents/section0.xml" media-type="application/xml"/>'
           '</o:manifest><o:spine><o:itemref idref="a" linear="no"/></o:spine></o:package>')
    package(path, xml, {'Contents/section0.xml': body('first@example.com')})
    assert 'first@example.com' in read_text(str(path))


@pytest.mark.parametrize('xml', [
    '<broken>', '<package/>',
    content([('a', 'Contents/section0.xml')], ['missing']),
    content([('a', 'Contents/section0.xml'), ('a', 'Contents/section1.xml')], ['a']),
    content([('a', 'Contents/section0.xml')], ['a', 'a']),
    content([('a', 'Contents/section0.xml'), ('b', 'Contents/section0.xml')], ['a', 'b']),
    content([('a', 'Contents/section0.xml')], []),
    content([('a', 'Contents/section0.xml')], ['a']).replace('<spine>', '<wrong>').replace('</spine>', '</wrong>'),
    content([('a', 'Contents/section0.xml')], ['a'], namespace='urn:unknown'),
])
def test_broken_package_never_falls_back_to_discovered_body(tmp_path, xml):
    path = tmp_path / 'broken.hwpx'
    package(path, xml, {'Contents/section0.xml': body('first@example.com')})
    check_failed(path)


@pytest.mark.parametrize('href', ['https://example.com/body.xml', '//example.com/body.xml',
                                 '/Contents/section0.xml', '../outside.xml',
                                 'Contents/section0.xml?query', 'Contents/section0.xml#fragment',
                                 'Contents\\section0.xml', 'C:/section0.xml',
                                 '%2e%2e/outside.xml', '%68ttps://example.com/body.xml', ''])
def test_unsafe_or_remote_spine_path_is_not_followed(tmp_path, href):
    path = tmp_path / 'unsafe.hwpx'
    package(path, content([('a', href)], ['a']), {'Contents/section0.xml': body('first@example.com')})
    check_failed(path)


def test_missing_declared_body_fails_after_available_body(tmp_path, capsys):
    path = tmp_path / 'missing.hwpx'
    xml = content([('a', 'Contents/section0.xml'), ('b', 'Contents/section1.xml')], ['a', 'b'])
    package(path, xml, {'Contents/section0.xml': body('first@example.com')})
    check_failed(path)
    output = tmp_path / 'output.txt'
    output.write_text('previous', encoding='utf-8')
    vault = tmp_path / 'vault.json'
    assert main([str(path), '--output', str(output), '--vault', str(vault), '--json-summary']) == 1
    report = json.loads(capsys.readouterr().err)
    assert report['error'] == 'document_extraction_incomplete'
    assert output.read_text(encoding='utf-8') == 'previous'
    assert not vault.exists()


def test_unreferenced_discovered_section_prevents_silent_omission(tmp_path):
    path = tmp_path / 'orphan.hwpx'
    package(path, content([('a', 'Contents/section0.xml')], ['a']),
            {'Contents/section0.xml': body('first@example.com'),
             'Contents/section1.xml': body('second@example.com')})
    check_failed(path)


@pytest.mark.parametrize('invalid', ['<wrong/>', '<sec xmlns="urn:unknown"/>', '<broken>'])
def test_unknown_spine_xml_is_not_treated_as_empty_supported_body(tmp_path, invalid):
    path = tmp_path / 'invalid-body.hwpx'
    package(path, content([('a', 'Contents/section0.xml'), ('b', 'Contents/section1.xml')], ['a', 'b']),
            {'Contents/section0.xml': body('first@example.com'), 'Contents/section1.xml': invalid})
    check_failed(path)


def test_manifest_without_body_is_not_success(tmp_path):
    path = tmp_path / 'no-body.hwpx'
    package(path, content([('header', 'Contents/header.xml')], ['header']),
            {'Contents/header.xml': f'<head xmlns="{HEAD}"/>'})
    check_failed(path)


def test_no_manifest_legacy_sections_use_numeric_order(tmp_path):
    path = tmp_path / 'legacy.hwpx'
    package(path, None, {f'Contents/section{i}.xml': body(f'row-{i:02d}') for i in reversed(range(12))})
    text = read_text(str(path))
    assert [text.index(f'row-{i:02d}') for i in range(12)] == sorted(text.index(f'row-{i:02d}') for i in range(12))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
@pytest.mark.parametrize('reader', [read_text_bounded, read_text_isolated])
def test_hpf_dtd_is_checked_before_new_metadata_parser(tmp_path, encoding, reader):
    path = tmp_path / 'dtd.hwpx'
    xml = '<?xml version="1.0" encoding="' + encoding + '"?><!DOCTYPE package [<!ENTITY x "first@example.com">]>'
    xml += content([('a', 'Contents/section0.xml')], ['a'], metadata='<title>&x;</title>')
    package(path, xml.encode(encoding), {'Contents/section0.xml': body('body text')})
    with pytest.raises(BoundedReadError) as error:
        reader(path)
    assert error.value.code == 'xml_dtd_rejected'


def test_cli_and_vault_include_declared_metadata(tmp_path, capsys):
    path = tmp_path / 'metadata.hwpx'
    package(path, content([('a', 'Contents/section0.xml')], ['a'],
                          metadata='<meta name="creator" content="text">author@example.com</meta>'),
            {'Contents/section0.xml': body('body@example.com')})
    output = tmp_path / 'out.txt'
    vault_path = tmp_path / 'vault.json'
    assert main([str(path), '--include', 'EMAIL', '--output', str(output), '--vault', str(vault_path)]) == 0
    text = Path(output).read_text(encoding='utf-8')
    assert 'author@example.com' not in text and 'body@example.com' not in text
    assert text.count('<EMAIL_') == 2
    vault = ReversibleVault.load(str(vault_path))
    assert vault.reveal('<EMAIL_1>') == 'author@example.com'
    assert vault.reveal('<EMAIL_2>') == 'body@example.com'
    assert 'author@example.com' not in capsys.readouterr().err


@pytest.mark.parametrize('target', [MANIFEST, 'META-INF/core.xml', 'Contents/core.xml', 'docProps/core.xml'])
def test_metadata_cannot_be_reinterpreted_as_body_text(tmp_path, target):
    path = tmp_path / 'recursive.hwpx'
    parts = {'Contents/section0.xml': body('first@example.com')}
    if target != MANIFEST:
        parts[target] = '<core><creator>author@example.com</creator></core>'
    package(path, content([('a', 'Contents/section0.xml'), ('b', target)], ['a', 'b']), parts)
    check_failed(path)


def test_ambiguous_root_and_relative_reference_is_rejected(tmp_path):
    path = tmp_path / 'ambiguous.hwpx'
    package(path, content([('a', 'body.xml')], ['a']),
            {'body.xml': body('first@example.com'), 'Contents/body.xml': body('second@example.com')})
    check_failed(path)


def test_batch_reports_manifest_failure_without_publishing_partial_text(tmp_path):
    path = tmp_path / 'missing.hwpx'
    package(path, content([('a', 'Contents/section0.xml'), ('b', 'Contents/section1.xml')], ['a', 'b']),
            {'Contents/section0.xml': body('first@example.com')})
    output = tmp_path / 'out'
    result = process_paths([str(path)], str(output), include=['EMAIL'], progress=False)
    assert result.succeeded == 0 and result.failed == 1
    assert result.results[0].error_code == 'document_extraction_incomplete'
    assert not list(output.rglob('*.txt'))


def test_manifest_metadata_counts_towards_text_limit(tmp_path):
    from ko_pii.io_.bounded import FileReadPolicy
    path = tmp_path / 'limited.hwpx'
    package(path, content([('a', 'Contents/section0.xml')], ['a'],
                          metadata='<meta name="creator" content="text">author@example.com</meta>'),
            {'Contents/section0.xml': body('x')})
    with pytest.raises(BoundedReadError) as error:
        read_text_bounded(path, policy=FileReadPolicy(max_text_chars=10))
    assert error.value.code == 'extracted_text_too_large'


@pytest.mark.parametrize('extra', ['<itemref xmlns="urn:unknown" idref="missing"/>',
                                  '<unknown idref="missing"/>'])
def test_unknown_spine_entry_does_not_hide_missing_reference(tmp_path, extra):
    path = tmp_path / 'unknown-entry.hwpx'
    xml = content([('a', 'Contents/section0.xml')], ['a']).replace('</spine>', extra + '</spine>')
    package(path, xml, {'Contents/section0.xml': body('first@example.com')})
    check_failed(path)


def test_duplicate_zip_manifest_is_rejected_by_low_level_inspection(tmp_path):
    path = tmp_path / 'duplicate.hwpx'
    xml = content([('a', 'Contents/section0.xml')], ['a'])
    package(path, xml, {'Contents/section0.xml': body('first@example.com')})
    with zipfile.ZipFile(path, 'a') as archive, pytest.warns(UserWarning):
        archive.writestr(MANIFEST, xml)
    check_failed(path)
