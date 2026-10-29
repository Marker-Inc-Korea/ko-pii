"""Worksheet discovery must follow the workbook, not guessed member names."""
from html import escape
import json
from pathlib import Path
import zipfile

import pytest

from ko_pii import Anonymizer
from ko_pii.batch import process_paths
from ko_pii.cli import main
from ko_pii.io_ import read_records, read_text, read_text_bounded, read_text_isolated
from ko_pii.io_.bounded import BoundedReadError, FileReadPolicy
from ko_pii.io_.coverage import DocumentExtractionError
from ko_pii.io_.xlsx import inspect_text


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
STRICT = "http://purl.oclc.org/ooxml/spreadsheetml/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SREL = "http://purl.oclc.org/ooxml/officeDocument/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
WORKBOOK = "xl/workbook.xml"
RELS = "xl/_rels/workbook.xml.rels"


def sheet(value, namespace=MAIN, shared=False):
    if shared:
        cells = ['<c t="s"><v>0</v></c>', '<c t="s"><v>1</v></c>']
    else:
        cells = [f'<c t="inlineStr"><is><t>{escape(text)}</t></is></c>' for text in ["email", value]]
    return f'<worksheet xmlns="{namespace}"><sheetData>' + "".join(
        f'<row r="{i}">{cell}</row>' for i, cell in enumerate(cells, 1)) + '</sheetData></worksheet>'


def package(namespace=MAIN, shared=False):
    relationship = SREL if namespace == STRICT else REL
    entries = [("2", "worksheets/sheet2.xml", "second@example.com"),
               ("1", "worksheets/sheet1.xml", "first@example.com")]
    parts = {
        WORKBOOK: f'<workbook xmlns="{namespace}" xmlns:r="{relationship}"><sheets>' + ''.join(
            f'<sheet name="Contacts{i}" sheetId="{i}" r:id="r{i}" state="hidden"/>'
            for i, _, _ in entries) + '</sheets></workbook>',
        RELS: f'<Relationships xmlns="{PKG}">' + ''.join(
            f'<Relationship Id="r{i}" Type="{relationship}/worksheet" Target="{path}"/>'
            for i, path, _ in entries) + (
                f'<Relationship Id="strings" Type="{relationship}/sharedStrings" Target="text/values.xml"/>'
                if shared else '') + '</Relationships>',
    }
    for _, path, value in entries:
        parts['xl/' + path] = sheet(value, namespace, shared)
    if shared:
        parts['xl/text/values.xml'] = f'<sst xmlns="{namespace}"><si><t>email</t></si>' \
                                     '<si><t>shared@example.com</t></si></sst>'
    return parts


def write(path, parts):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, text in parts.items():
            archive.writestr(name, text)
    return path


@pytest.mark.parametrize('namespace', [MAIN, STRICT])
@pytest.mark.parametrize('reader', [read_records, read_text, read_text_bounded, read_text_isolated])
def test_workbook_order_not_filename_order(tmp_path, namespace, reader):
    path = write(tmp_path / 'order.xlsx', package(namespace))
    result = reader(str(path))
    if isinstance(result, list):
        assert result == [{'email': 'second@example.com'}, {'email': 'first@example.com'}]
    else:
        text = result if isinstance(result, str) else result.text
        assert text.index('second@example.com') < text.index('first@example.com')


@pytest.mark.parametrize('target,name', [
    ('worksheets/contacts.xml', 'xl/worksheets/contacts.xml'),
    ('/xl/custom/contacts.xml', 'xl/custom/contacts.xml'),
    ('../custom/contacts.xml', 'custom/contacts.xml'),
    ('custom/contact%20list.xml', 'xl/custom/contact list.xml'),
])
@pytest.mark.parametrize('reader', [read_records, read_text_bounded, read_text_isolated])
def test_relationship_targets_can_have_noncanonical_names(tmp_path, target, name, reader):
    parts = package()
    parts[RELS] = parts[RELS].replace('worksheets/sheet2.xml', target)
    parts[name] = parts.pop('xl/worksheets/sheet2.xml')
    result = reader(str(write(tmp_path / 'names.xlsx', parts)))
    assert 'second@example.com' in (repr(result) if isinstance(result, list) else result.text)


@pytest.mark.parametrize('namespace', [MAIN, STRICT])
@pytest.mark.parametrize('reader', [read_records, read_text, read_text_bounded, read_text_isolated])
def test_shared_strings_are_loaded_from_relationship(tmp_path, namespace, reader):
    path = write(tmp_path / 'strings.xlsx', package(namespace, shared=True))
    result = reader(str(path))
    assert 'shared@example.com' in (result if isinstance(result, str) else repr(result))


@pytest.mark.parametrize('fault', [
    'missing_sheet', 'missing_relationship', 'missing_workbook', 'bad_workbook',
    'bad_rels', 'bad_namespace', 'unknown_id', 'duplicate_id', 'duplicate_target',
    'duplicate_sheet_id', 'duplicate_sheet_name', 'external', 'remote', 'escape_root',
    'fragment', 'backslash', 'unknown_type', 'unlisted_sheet', 'unlisted_relationship',
    'missing_strings', 'duplicate_strings', 'conflicting_strings', 'missing_sheets',
])
def test_broken_package_never_returns_partial_success(tmp_path, fault):
    parts = package(shared=fault.endswith('strings'))
    if fault == 'missing_sheet':
        del parts['xl/worksheets/sheet2.xml']
    elif fault == 'missing_relationship':
        del parts[RELS]
    elif fault == 'missing_workbook':
        del parts[WORKBOOK]
    elif fault == 'bad_workbook':
        parts[WORKBOOK] = '<workbook'
    elif fault == 'bad_rels':
        parts[RELS] = '<Relationships'
    elif fault == 'bad_namespace':
        parts[WORKBOOK] = parts[WORKBOOK].replace(MAIN, 'urn:unknown')
    elif fault == 'unknown_id':
        parts[WORKBOOK] = parts[WORKBOOK].replace('r:id="r2"', 'r:id="absent"')
    elif fault == 'duplicate_id':
        parts[RELS] = parts[RELS].replace('Id="r1"', 'Id="r2"')
    elif fault == 'duplicate_target':
        parts[RELS] = parts[RELS].replace('sheet2.xml', 'sheet1.xml')
    elif fault == 'duplicate_sheet_id':
        parts[WORKBOOK] = parts[WORKBOOK].replace('sheetId="2"', 'sheetId="1"')
    elif fault == 'duplicate_sheet_name':
        parts[WORKBOOK] = parts[WORKBOOK].replace('Contacts2', 'Contacts1')
    elif fault == 'external':
        parts[RELS] = parts[RELS].replace('Id="r2"', 'Id="r2" TargetMode="External"')
    elif fault in {'remote', 'escape_root', 'fragment', 'backslash'}:
        target = {'remote': 'https://example.com/private.xml', 'escape_root': '../../escape.xml',
                  'fragment': 'worksheets/sheet2.xml#part', 'backslash': r'worksheets\sheet2.xml'}[fault]
        parts[RELS] = parts[RELS].replace('worksheets/sheet2.xml', target)
    elif fault == 'unknown_type':
        parts[RELS] = parts[RELS].replace('/worksheet', '/chartsheet')
    elif fault == 'unlisted_sheet':
        parts['xl/worksheets/sheet3.xml'] = sheet('third@example.com')
    elif fault == 'unlisted_relationship':
        parts[RELS] = parts[RELS].replace('</Relationships>',
            f'<Relationship Id="unused" Type="{REL}/worksheet" Target="custom.xml"/></Relationships>')
    elif fault == 'missing_strings':
        del parts['xl/text/values.xml']
    elif fault == 'duplicate_strings':
        parts[RELS] = parts[RELS].replace('</Relationships>',
            f'<Relationship Id="other" Type="{REL}/sharedStrings" Target="other.xml"/></Relationships>')
    elif fault == 'conflicting_strings':
        parts['xl/sharedStrings.xml'] = parts['xl/text/values.xml']
    elif fault == 'missing_sheets':
        parts[WORKBOOK] = f'<workbook xmlns="{MAIN}"/>'
    path = write(tmp_path / 'broken.xlsx', parts)
    with pytest.raises(ValueError):
        read_records(str(path))
    inspection = inspect_text(str(path))
    assert inspection.coverage['status'] in {'partial', 'failed'}
    assert '@example.com' not in repr(inspection.coverage)
    with pytest.raises(DocumentExtractionError):
        inspection.require_complete()


def test_missing_declared_sheet_cli_preserves_existing_output(tmp_path, capsys):
    parts = package()
    del parts['xl/worksheets/sheet2.xml']
    path = write(tmp_path / 'broken.xlsx', parts)
    output, vault = tmp_path / 'out.txt', tmp_path / 'vault.json'
    output.write_text('previous result', encoding='utf-8')
    assert main([str(path), '--output', str(output), '--vault', str(vault), '--json-summary']) == 1
    report = json.loads(capsys.readouterr().err)
    assert report['error'] == 'document_extraction_incomplete'
    assert output.read_text(encoding='utf-8') == 'previous result'
    assert not vault.exists()


def test_token_order_matches_workbook_and_restores(tmp_path):
    path = write(tmp_path / 'ordered.xlsx', package())
    result = Anonymizer(include=['EMAIL']).process(read_text_bounded(path).text)
    assert result.vault.reveal('<EMAIL_1>') == 'second@example.com'
    assert result.vault.reveal('<EMAIL_2>') == 'first@example.com'


def test_legacy_without_workbook_uses_numeric_sheet_order(tmp_path):
    parts = {f'xl/worksheets/sheet{i}.xml': sheet(f'p{i}@example.com') for i in range(1, 13)}
    records = read_records(str(write(tmp_path / 'legacy.xlsx', parts)))
    assert [row['email'] for row in records] == [f'p{i}@example.com' for i in range(1, 13)]


@pytest.mark.parametrize('name', [WORKBOOK, RELS, 'xl/worksheets/sheet2.xml', 'xl/text/values.xml'])
def test_duplicate_member_rejected_in_low_level_reader(tmp_path, name):
    parts = package(shared=True)
    path = write(tmp_path / 'duplicate.xlsx', parts)
    with zipfile.ZipFile(path, 'a') as archive, pytest.warns(UserWarning, match='Duplicate'):
        archive.writestr(name, parts[name])
    with pytest.raises(ValueError, match='relationships'):
        read_records(str(path))
    assert inspect_text(str(path)).coverage['status'] == 'failed'


@pytest.mark.parametrize('reader', [read_text_bounded, read_text_isolated])
@pytest.mark.parametrize('name', [WORKBOOK, RELS, 'xl/text/values.xml'])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16'])
def test_relationship_xml_stays_under_dtd_preflight(tmp_path, reader, name, encoding):
    parts = package(shared=True)
    parts[name] = ('<?xml version="1.0" encoding="' + encoding + '"?>'
                   '<!DOCTYPE item [<!ENTITY secret "private@example.com">]><item>&secret;</item>').encode(encoding)
    path = write(tmp_path / 'dtd.xlsx', parts)
    with pytest.raises(BoundedReadError) as error:
        reader(path)
    assert error.value.code == 'xml_dtd_rejected'


@pytest.mark.parametrize('reader', [read_text_bounded, read_text_isolated])
def test_renamed_sheet_still_has_text_limit(tmp_path, reader):
    parts = package()
    parts[RELS] = parts[RELS].replace('worksheets/sheet2.xml', 'worksheets/contacts.xml')
    parts['xl/worksheets/contacts.xml'] = parts.pop('xl/worksheets/sheet2.xml')
    with pytest.raises(BoundedReadError) as error:
        reader(write(tmp_path / 'limit.xlsx', parts), policy=FileReadPolicy(max_text_chars=10))
    assert error.value.code == 'extracted_text_too_large'


def test_missing_sheet_batch_fails_only_broken_input(tmp_path):
    good = write(tmp_path / 'good.xlsx', package())
    parts = package()
    del parts['xl/worksheets/sheet2.xml']
    bad = write(tmp_path / 'bad.xlsx', parts)
    output = tmp_path / 'output'
    result = process_paths([str(good), str(bad)], str(output), progress=False)
    assert result.succeeded == 1 and result.failed == 1
    bad_result = next(row for row in result.results if row.input_path == str(bad))
    good_result = next(row for row in result.results if row.input_path == str(good))
    assert bad_result.error_code == 'document_extraction_incomplete'
    assert bad_result.output_path is None
    assert good_result.error is None and good_result.output_path is not None
    assert list(output.iterdir()) == [Path(good_result.output_path)]


@pytest.mark.parametrize('target', ['https://example.com/values.xml', '../../values.xml',
                                   'text/values.xml#part', 'text/%invalid.xml'])
def test_invalid_shared_string_target_is_not_followed(tmp_path, target):
    parts = package(shared=True)
    parts[RELS] = parts[RELS].replace('text/values.xml', target)
    path = write(tmp_path / 'strings.xlsx', parts)
    with pytest.raises(DocumentExtractionError):
        read_text(str(path))


def test_unrelated_relationships_are_not_fetched(tmp_path):
    parts = package()
    parts[RELS] = parts[RELS].replace('</Relationships>',
        f'<Relationship Id="unused" Type="{REL}/externalLink" TargetMode="External" '
        'Target="https://example.com/not-fetched"/></Relationships>')
    assert len(read_records(str(write(tmp_path / 'external.xlsx', parts)))) == 2
