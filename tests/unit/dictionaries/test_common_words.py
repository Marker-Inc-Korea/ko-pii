from ko_pii.dictionaries.common_words import is_common_word


def test_known_false_positives():
    for w in ("김치", "박물관", "장관", "한국", "서울"):
        assert is_common_word(w)


def test_real_names_not_in_dictionary():
    for w in ("길동", "철수", "영희", "민수"):
        assert not is_common_word(w)
