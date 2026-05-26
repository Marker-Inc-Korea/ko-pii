from ko_pii.dictionaries.surnames import (
    KOREAN_SURNAMES,
    is_surname,
    surname_prefix_len,
)


def test_common_surnames_present():
    for s in ("김", "이", "박", "최", "정"):
        assert is_surname(s)


def test_compound_surnames_present():
    for s in ("남궁", "황보", "선우", "제갈"):
        assert is_surname(s)


def test_non_surnames_absent():
    for w in ("길동", "철수", "영희"):
        assert not is_surname(w)


def test_prefix_len_compound_wins():
    assert surname_prefix_len("남궁민수") == 2
    assert surname_prefix_len("황보경") == 2
    assert surname_prefix_len("김철수") == 1
    # "철" is not a Korean surname → no prefix
    assert surname_prefix_len("철수") == 0


def test_dictionary_size_reasonable():
    # We seed at least ~140 unique surnames.
    assert len(KOREAN_SURNAMES) >= 140
