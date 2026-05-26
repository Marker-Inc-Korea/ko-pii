from ko_pii.dictionaries.titles import TITLES, TITLES_GOV, is_title, is_gov_title


def test_gov_titles_recognized():
    for t in ("장관", "차관", "사무관", "주무관", "과장"):
        assert is_title(t)
        assert is_gov_title(t)


def test_civilian_titles_recognized():
    for t in ("대표이사", "교수", "의사", "변호사"):
        assert is_title(t)


def test_unknown_passthrough():
    assert not is_title("게임디자이너")
    assert not is_gov_title("교수")


def test_dictionary_sizes():
    assert len(TITLES_GOV) >= 40
    assert len(TITLES) >= 30
