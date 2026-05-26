from ko_pii.context.name_dictionary import NameDictionary


def test_add_and_lookup():
    d = NameDictionary()
    d.add("홍길동", 0.85, (10, 13), evidence=["pos:field_label(성명)"])
    assert d.known("홍길동")
    assert d.boost_for("홍길동") > 0
    assert d.boost_for("unknown") == 0.0


def test_occurrences_accumulate():
    d = NameDictionary()
    d.add("홍길동", 0.85, (10, 13))
    d.add("홍길동", 0.6, (50, 53))
    rec = d.names()[0]
    assert rec.occurrences == [(10, 13), (50, 53)]
    # Max-confidence wins
    assert rec.confidence == 0.85


def test_boost_is_capped():
    d = NameDictionary()
    d.add("홍길동", 1.0, (0, 3))
    assert d.boost_for("홍길동") <= 0.4
