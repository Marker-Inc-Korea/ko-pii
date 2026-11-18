"""Generated valid annotations exercise evaluation validation and output states."""
from hypothesis import given, settings, strategies as st

from ko_pii import ProcessingMode
from ko_pii.eval.domain import LabeledDocument, compare_reports, evaluate
from ko_pii.eval.synth import GoldDocument, GoldSpan


@st.composite
def documents(draw):
    prefix = draw(st.text(alphabet="문서 abc\n\t💡\u0301", max_size=12))
    phone = draw(st.sampled_from(["010-1234-5678", "０１０-１２３４-５６７８", "010-12\u200b34-5678"]))
    text = prefix + phone + " / " + phone
    coordinates = draw(st.sets(st.tuples(
        st.sampled_from(["PHONE", "PERSON", "EMAIL"]),
        st.integers(min_value=0, max_value=len(text) - 1),
        st.integers(min_value=1, max_value=len(text)),
    ).filter(lambda item: item[1] < item[2]), max_size=6))
    spans = [GoldSpan(label, start, end, text[start:end]) for label, start, end in sorted(coordinates)]
    return LabeledDocument("generated", GoldDocument(text, spans))


@settings(max_examples=60, deadline=None, derandomize=True)
@given(document=documents(), mode=st.sampled_from(list(ProcessingMode)),
       strategy=st.sampled_from(["redact", "tokenize", "partial", "hashed"]))
def test_valid_python_reports_remain_self_comparable(document, mode, strategy):
    original = [(s.label, s.start, s.end, s.text) for s in document.gold.spans]
    report = evaluate([document], labels=["PHONE", "PERSON", "EMAIL"],
                      output_mode=mode, output_strategy=strategy)
    result = compare_reports(report, report)
    assert all(value == 0 for value in result["counts"].values())
    assert result["output"] == {"changes": [], "new_not_fully_replaced": 0,
                                "resolved_not_fully_replaced": 0}
    assert sum(report["output_evaluation"]["counts"].values()) == len(original)
    assert original == [(s.label, s.start, s.end, s.text) for s in document.gold.spans]
