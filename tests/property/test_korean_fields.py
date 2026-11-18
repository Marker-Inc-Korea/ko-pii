"""Generated Korean record boundaries and explicit person declarations."""
import unicodedata

from hypothesis import given, settings, strategies as st

from ko_pii import Anonymizer


@settings(max_examples=200, deadline=None, derandomize=True)
@given(surname=st.sampled_from(["김", "이", "박", "남궁", "제갈"]),
       given_name=st.tuples(st.sampled_from(["다", "보", "지", "하", "태"]),
                            st.sampled_from(["은", "라", "성", "부", "로", "인"])),
       line=st.sampled_from(["\n", "\r", "\r\n", "\v", "\f", "\x85", "\u2028", "\u2029", "\n\n"]),
       quotes=st.sampled_from([("", ""), ("\"", "\""), ("“", "”"), ("「", "」")]),
       form=st.sampled_from(["NFC", "NFD"]))
def test_a_labeled_name_keeps_its_entire_source_range(surname, given_name, line, quotes, form):
    name = surname + "".join(given_name)
    prefix = unicodedata.normalize(form, "\ufb03 성명:" + line + quotes[0])
    raw = unicodedata.normalize(form, name)
    suffix = quotes[1] + line + "주소: 서울"
    source = prefix + raw + suffix
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + "[성명]" + suffix
    assert [(r.detection.start, r.detection.end, r.detection.text) for r in result.detections] == [
        (len(prefix), len(prefix) + len(raw), raw),
    ]


@settings(max_examples=200, deadline=None, derandomize=True)
@given(surname=st.sampled_from(["김", "이", "박", "남궁", "제갈"]),
       given_name=st.tuples(st.sampled_from(["다", "보", "지", "하", "태"]),
                            st.sampled_from(["은", "라", "성", "부", "로", "인"])),
       role=st.sampled_from(["신청인", "담당자", "작성자", "보호자"]),
       form=st.sampled_from(["NFC", "NFD"]))
def test_an_explicit_role_declaration_keeps_the_name_before_its_copula(surname, given_name, role, form):
    topic = "은" if (ord(role[-1]) - 0xAC00) % 28 else "는"
    prefix = unicodedata.normalize(form, role + topic + " ")
    raw = unicodedata.normalize(form, surname + "".join(given_name))
    suffix = unicodedata.normalize(form, "입니다.")
    source = prefix + raw + suffix
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + "[성명]" + suffix


@settings(max_examples=200, deadline=None, derandomize=True)
@given(names=st.lists(st.sampled_from(["김다은", "이지은", "박보라", "김태성", "남궁다은", "조성"]),
                     min_size=2, max_size=8),
       separator=st.sampled_from([", ", " / ", "·", "-", " & "]),
       wrapper=st.sampled_from([("", ""), ('"', '"'), ("**", "**"), ("`", "`")]),
       form=st.sampled_from(["NFC", "NFD"]))
def test_name_list_replacement_keeps_all_original_separators(names, separator, wrapper, form):
    prefix = unicodedata.normalize(form, "[성명] ")
    raw_names = [unicodedata.normalize(form, name) for name in names]
    source = prefix + separator.join(wrapper[0] + name + wrapper[1] for name in raw_names)
    result = Anonymizer(strategy="redact", include=["PERSON"]).process(source)
    assert result.text == prefix + separator.join(wrapper[0] + "[성명]" + wrapper[1] for _ in names)
    assert [source[item.detection.start:item.detection.end] for item in result.detections] == raw_names
