from ko_pii.eval.synth import GoldDocument, generate_document, generate_corpus


def test_generate_document_is_deterministic_with_seed():
    a = generate_document(seed=42)
    b = generate_document(seed=42)
    assert a.text == b.text
    assert [(s.label, s.start, s.end) for s in a.spans] == \
           [(s.label, s.start, s.end) for s in b.spans]


def test_gold_spans_match_text():
    doc = generate_document(seed=1)
    for s in doc.spans:
        assert doc.text[s.start:s.end] == s.text


def test_each_template():
    for tmpl in ("gov_decree", "civil_petition", "hr_review", "meeting_minutes"):
        doc = generate_document(seed=7, template=tmpl)
        assert doc.template == tmpl
        assert len(doc.spans) > 0


def test_unknown_template_raises():
    import pytest
    with pytest.raises(ValueError):
        generate_document(template="nope")


def test_corpus_size_and_diversity():
    corpus = generate_corpus(10, seed=0)
    assert len(corpus) == 10
    templates = {d.template for d in corpus}
    # With 10 docs we should see at least 2 different templates
    assert len(templates) >= 2
