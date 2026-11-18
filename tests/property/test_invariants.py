"""Synthetic invariants, not a real-domain accuracy or privacy benchmark."""
from hypothesis import given, settings, strategies as st
import unicodedata

from ko_pii import Anonymizer, DetectionResult, RegexDetector, ReversibleVault, RiskLevel, anonymize_json
from ko_pii.core.modes import ProcessingMode
from ko_pii.core.overlap import resolve_overlaps
from ko_pii.core.trace import OverlapTrace


generated = settings(max_examples=200, derandomize=True, deadline=None, database=None)


@generated
@given(surname=st.sampled_from(["김", "이", "박", "최", "남궁", "제갈"]),
       given_first=st.sampled_from(["다", "보", "지", "태", "수", "민", "하"]),
       given_last=st.sampled_from(["은", "라", "성", "부", "로", "인", "운", "임"]),
       form=st.sampled_from(["NFC", "NFD"]),
       mode=st.sampled_from([ProcessingMode.STRICT, ProcessingMode.BALANCED, ProcessingMode.PARANOID]))
def test_bounded_person_field_preserves_all_name_syllables(surname, given_first, given_last, form, mode):
    name = unicodedata.normalize(form, surname + given_first + given_last)
    prefix = unicodedata.normalize(form, "성명: ")
    source = prefix + name + "\npublic"
    result = Anonymizer(include=["PERSON"], strategy="redact", mode=mode).process(source)
    assert result.text == prefix + "[성명]\npublic"
    assert len(result.detections) == 1
    detection = result.detections[0].detection
    assert (detection.start, detection.end, detection.text) == (len(prefix), len(prefix) + len(name), name)


@generated
@given(digits=st.text(alphabet="0123456789", min_size=8, max_size=8),
       fullwidth=st.lists(st.booleans(), min_size=8, max_size=8),
       separator=st.sampled_from(["", "\u200b", "\u00ad"]),
       prefix=st.sampled_from(["", "😀 연락처: ", "문서\n전화: "]))
def test_phone_source_output_spans_and_normalization(digits, fullwidth, separator, prefix):
    noisy = "".join(chr(ord(c) + 0xFEE0) if wide else c for c, wide in zip(digits, fullwidth))
    phone = "010-" + noisy[:4] + "-" + noisy[4:]
    phone = phone[:6] + separator + phone[6:]
    text = prefix + phone + " 끝"
    result = Anonymizer(include=["PHONE"], strategy="redact").process(text)
    assert result.text == prefix + "[전화번호] 끝"
    for record in result.detections:
        d = record.detection
        assert text[d.start:d.end] == d.text
    for span in result.substitutions:
        assert result.text[span.output_start:span.output_end] == "[전화번호]"


@generated
@given(local=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=20),
       at=st.sampled_from(["@", " [at] ", " (AT) ", "\t@\t"]),
       dot=st.sampled_from([".", " [dot] ", " (dot) "]),
       prefix=st.sampled_from(["Please email ", "README\nContact\n", "문서\x85", "문서\u2028"]))
def test_obfuscated_email_preserves_prose_and_lines(local, at, dot, prefix):
    value = local + at + "example" + dot + "com"
    result = Anonymizer(include=["EMAIL"], strategy="redact").process(prefix + value)
    assert result.text == prefix + "[이메일]"
    assert result.detections[0].detection.text == value


@generated
@given(rows=st.lists(st.tuples(st.sampled_from(["PERSON", "EMAIL", "PHONE"]),
                             st.text(alphabet="abc가나다0123", min_size=1, max_size=20)), max_size=30))
def test_vault_roundtrip_mapping_and_next_token(rows):
    vault = ReversibleVault()
    tokens = [vault.store(label=label, original=value, risk_level=4) for label, value in rows]
    restored = ReversibleVault.loads(vault.dumps())
    for (label, value), token in zip(rows, tokens):
        assert restored.reveal(token) == value
        assert restored.store(label=label, original=value, risk_level=4) == token
    fresh = restored.store(label="PHONE", original="new-synthetic-value", risk_level=4)
    assert fresh not in tokens
    assert restored.reveal(fresh) == "new-synthetic-value"


@generated
@given(rows=st.lists(st.tuples(st.integers(0, 100), st.integers(1, 30),
                             st.integers(1, 5), st.sampled_from([0.0, 0.5, 1.0])), max_size=60),
       cap=st.integers(0, 10))
def test_overlap_index_matches_pairwise_oracle_with_and_without_trace(rows, cap):
    items = [DetectionResult("PHONE", "synthetic", start, start + length, RiskLevel(risk), confidence)
             for start, length, risk, confidence in rows]
    ordered = sorted(items, key=lambda d: (-int(d.risk_level), -d.confidence, -d.length, d.start))
    expected = []
    for d in ordered:
        if not any(d.start < a.end and a.start < d.end for a in expected):
            expected.append(d)
    expected.sort(key=lambda d: (d.start, d.end))
    trace = OverlapTrace(cap)
    assert resolve_overlaps(items, trace=trace) == expected == resolve_overlaps(items)
    assert len(trace.report()["discarded"]) <= cap
    assert trace.report()["omitted_events"] == max(0, len(items) - len(expected) - cap)


@generated
@given(value=st.text(alphabet="가나다라마바", min_size=2, max_size=6),
       key=st.text(alphabet="a/~01", min_size=1, max_size=12))
def test_field_exclusions_never_propagate_to_other_fields_or_assertions(value, key):
    import re
    anon = Anonymizer(include=["PERSON"], strategy="asterisk",
                      secondary_detector=RegexDetector(re.escape(value), label="PERSON"))
    path = "/" + key.replace("~", "~0").replace("/", "~1")
    result = anonymize_json({key: value, "customer": value}, anonymizer=anon,
                            field_person_exclusions={path: [value]}, field_labels={"/customer": "PERSON"})
    assert result.data == {key: value, "customer": "*" * len(value)}
    assert anon.process(value).text == "*" * len(value)
