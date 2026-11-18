"""Generated form syntax and Unicode-header lookup keep original text and keys."""
import unicodedata

from hypothesis import given, settings, strategies as st

from ko_pii import Anonymizer
from ko_pii.tabular import anonymize_records, map_columns


@settings(max_examples=200, deadline=None, derandomize=True)
@given(name=st.sampled_from(["김빛나라", "장피에르뒤퐁", "John Smith", "金民秀", "Anne-Marie O'Neill"]),
       field=st.sampled_from(["전화번호", "생년월일", "이메일", "계좌번호", "비고", "Phone"]),
       frame=st.sampled_from([("", ""), ("**", "**"), ("__", "__"), ("`", "`"), ("[", "]")]),
       annotation=st.sampled_from(["", "(회사)", "(양력)", "(work)"]),
       outside=st.booleans(), spaces=st.integers(min_value=1, max_value=6), form=st.sampled_from(["NFC", "NFD"]))
def test_form_names_preserve_every_character_outside_the_name(name, field, frame, annotation, outside, spaces, form):
    raw = unicodedata.normalize(form, name)
    prefix = unicodedata.normalize(form, "성명: ")
    key = (frame[0] + field + frame[1] + annotation if outside else frame[0] + field + annotation + frame[1])
    suffix = " " * spaces + unicodedata.normalize(form, key) + ": public"
    source = prefix + raw + suffix
    result = Anonymizer(include=["PERSON"], strategy="redact").process(source)
    assert result.text == prefix + "[성명]" + suffix
    assert [(r.detection.start, r.detection.end, r.detection.text) for r in result.detections] == [
        (len(prefix), len(prefix) + len(raw), raw),
    ]


@settings(max_examples=200, deadline=None, derandomize=True)
@given(prefix=st.sampled_from(["", "customer_", "product_"]), fullwidth=st.booleans(),
       positions=st.sets(st.integers(min_value=0, max_value=20)),
       invisible=st.sampled_from(["\u200b", "\u200d", "\ufeff"]))
def test_normalized_header_lookup_does_not_change_keys_or_enable_unknown_prefixes(prefix, fullwidth, positions, invisible):
    source = prefix + "email"
    if fullwidth:
        source = "".join(chr(ord(char) + 0xFEE0) for char in source)
    header = "".join(char + (invisible if index in positions else "") for index, char in enumerate(source))
    records = [{header: "demo@example.com", "memo": "public"}]
    if prefix == "product_":
        assert map_columns([header]) == {}
        assert anonymize_records(records, strategy="redact")[0] == records
    else:
        assert map_columns([header]) == {header: "EMAIL"}
        assert anonymize_records(records, strategy="redact")[0] == [{header: "[이메일]", "memo": "public"}]
