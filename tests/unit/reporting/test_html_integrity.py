"""Source binding and occurrence-scoped, value-free HTML review downloads."""
import copy
from dataclasses import replace
from html.parser import HTMLParser
import json
import shutil
import subprocess
from uuid import UUID

import pytest

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.core.modes import Action
from ko_pii.reporting.html_report import generate_html_report


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.findings = []
        self.metadata = None
        self.script = ""
        self.current_script = None
        self.feed(text)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "span" and "data-finding-id" in attrs:
            self.findings.append(attrs)
        if tag == "script":
            self.current_script = "metadata" if attrs.get("id") == "reviewMetadata" else "javascript"

    def handle_data(self, text):
        if self.current_script == "metadata":
            self.metadata = json.loads(text)
        elif self.current_script == "javascript":
            self.script += text

    def handle_endtag(self, tag):
        if tag == "script":
            self.current_script = None


SOURCE = "첫 요청: 880101-1234567 / 두 번째 요청: 880101-1234567"


def review_page():
    result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(SOURCE)
    assert len(result.review_items()) == 2
    return Page(generate_html_report(SOURCE, result, document_id="sensitive-document-id"))


RUNNER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
let download = null;
let revoked = false;
const counter = {textContent: '0'};
const buttons = input.findings.map(attrs => {
  const span = {dataset: {findingId: attrs['data-finding-id'], label: attrs['data-label'],
    reviewLabel: attrs['data-review-label'],
    start: attrs['data-start'], end: attrs['data-end'], token: attrs['data-token']}, style: {}};
  const parent = {previousElementSibling: span, children: []};
  parent.children = ['OK', 'FP'].map(verdict => ({parentElement: parent, verdict,
    attributes: {'aria-pressed': 'false'}, setAttribute(name, value) { this.attributes[name] = value; }}));
  return parent.children;
});
const context = vm.createContext({
  document: {
    getElementById(id) { return id === 'reviewMetadata' ? {textContent: JSON.stringify(input.metadata)} : counter; },
    createElement() { return {click() {}}; }
  },
  Blob: class {constructor(parts) { download = JSON.parse(parts.join('')); }},
  URL: {createObjectURL() {return 'blob:local';}, revokeObjectURL() {revoked = true;}},
  setTimeout(callback) {callback();}
});
vm.runInContext(input.script, context);
for (const operation of input.operations) {
  const pair = buttons[operation.index];
  context.mark(pair[operation.verdict === 'FP' ? 1 : 0], operation.verdict);
}
context.exportMarks();
process.stdout.write(JSON.stringify({download, count: counter.textContent, revoked,
  pressed: buttons.map(pair => pair.map(button => button.attributes['aria-pressed']))}));
"""


def interact(page, operations):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js required to exercise the generated report JavaScript")
    completed = subprocess.run([node, "-e", RUNNER], input=json.dumps({
        "findings": page.findings, "metadata": page.metadata, "script": page.script,
        "operations": operations,
    }), capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    return json.loads(completed.stdout)


def test_repeated_values_keep_independent_occurrence_decisions():
    page = review_page()
    observed = interact(page, [{"index": 1, "verdict": "FP"}, {"index": 0, "verdict": "OK"}])
    payload = observed["download"]
    assert payload["contract"] == "ko-pii-html-review-marks-v1" and payload["schema_version"] == 1
    assert payload["scope"] == "selected_occurrences_only"
    assert payload["offset_unit"] == "python_code_points"
    assert UUID(payload["report_id"]).version == 4
    assert payload["source_characters"] == len(SOURCE)
    assert [item["verdict"] for item in payload["items"]] == ["OK", "FP"]
    assert [item["source_span"] for item in payload["items"]] == [[6, 20], [32, 46]]
    assert len({item["finding_id"] for item in payload["items"]}) == 2
    assert observed["count"] == "2" and observed["revoked"]
    assert observed["pressed"] == [["true", "false"], ["false", "true"]]
    assert "880101" not in json.dumps(payload) and "sensitive-document-id" not in json.dumps(payload)


def test_revising_one_occurrence_does_not_change_another():
    observed = interact(review_page(), [{"index": 0, "verdict": "OK"}, {"index": 1, "verdict": "OK"},
                                        {"index": 0, "verdict": "FP"}])
    assert [item["verdict"] for item in observed["download"]["items"]] == ["FP", "OK"]
    assert observed["count"] == "2"


def test_empty_or_invalid_marks_do_not_claim_completion():
    observed = interact(review_page(), [{"index": 0, "verdict": "APPROVED"}])
    assert observed["download"]["items"] == [] and observed["count"] == "0"
    assert observed["download"]["scope"] == "selected_occurrences_only"


def test_metadata_is_report_specific_and_contains_no_document_identifier():
    first, second = review_page(), review_page()
    assert first.metadata["report_id"] != second.metadata["report_id"]
    assert set(first.metadata) == {"schema_version", "contract", "report_id", "scope", "offset_unit", "source_characters"}


def test_custom_category_metadata_is_not_copied_into_value_free_downloads():
    result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(SOURCE)
    result.detections[0].detection.label = "sensitive-user-name"
    page = Page(generate_html_report(SOURCE, result))
    observed = interact(page, [{"index": 0, "verdict": "OK"}])["download"]
    assert observed["items"][0]["label"] == "UNKNOWN"
    assert "sensitive-user-name" not in json.dumps(observed)


@pytest.mark.parametrize("change", ["wrong-pii", "prefix", "suffix", "output", "missing-trace", "reversed-trace",
                                   "negative", "bool", "past-source", "past-output", "wrong-action"])
def test_mismatched_source_and_result_are_rejected_without_raw_values(change):
    text = "연락: 010-2345-6789 / 메일: a@example.com 끝"
    result = Anonymizer().process(text)
    source = text
    if change == "wrong-pii":
        source = text.replace("2345", "3456")
    elif change == "prefix":
        source = text.replace("연락", "안내")
    elif change == "suffix":
        source = text + "!"
    elif change == "output":
        result.text += "!"
    elif change == "missing-trace":
        result.substitutions.clear()
    elif change == "reversed-trace":
        result.substitutions.reverse()
    elif change == "wrong-action":
        result.detections[0].action = Action.REVIEW
    else:
        key, value = {"negative": ("start", -1), "bool": ("start", True),
                      "past-source": ("end", len(text) + 1), "past-output": ("output_end", len(result.text) + 1)}[change]
        result.substitutions[0] = replace(result.substitutions[0], **{key: value})
    with pytest.raises(ValueError, match="matching source") as exc:
        generate_html_report(source, result)
    assert "010-2345-6789" not in str(exc.value) and "a@example.com" not in str(exc.value)


@pytest.mark.parametrize("mode", list(ProcessingMode))
@pytest.mark.parametrize("strategy", ["redact", "tokenize", "asterisk", "partial", "hashed", "fpe"])
def test_matching_unicode_results_are_supported_without_mutation(mode, strategy):
    text = "💡 연락처: ０１０-２３４５-６７８９ / 성명: John Smith"
    result = Anonymizer(mode=mode, strategy=strategy).process(text)
    before = copy.deepcopy((result.text, result.detections, result.substitutions, result.summary))
    page = generate_html_report(text, result)
    assert "원문 개인정보가 포함" in page
    assert before == (result.text, result.detections, result.substitutions, result.summary)


def test_html_and_exports_do_not_execute_user_markup():
    text = '</script><img src=x onerror="alert(1)"> a@example.com'
    result = Anonymizer().process(text)
    result.summary["combined_risk"] = '"><img src=x onerror="alert(2)">'
    page = generate_html_report(text, result, document_id='</title><script>alert(3)</script>')
    assert '<img src=x' not in page and '<script>alert' not in page
    parsed = Page(page)
    exported = interact(parsed, [])["download"]
    assert "alert" not in json.dumps(exported)


def test_marking_can_be_disabled_and_empty_documents_are_valid():
    page = generate_html_report("", Anonymizer().process(""), enable_marking=False)
    assert "<script" not in page and 'onclick=' not in page
    assert Page(page).metadata is None
    assert "원문 개인정보가 포함" in page
