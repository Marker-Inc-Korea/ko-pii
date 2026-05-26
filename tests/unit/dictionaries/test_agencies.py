from ko_pii.dictionaries.agencies import AGENCIES, is_agency


def test_ministries():
    for a in ("기획재정부", "행정안전부", "법무부", "보건복지부"):
        assert is_agency(a)


def test_local_governments():
    for a in ("서울특별시", "경기도", "제주특별자치도"):
        assert is_agency(a)


def test_judicial():
    for a in ("대법원", "헌법재판소", "감사원"):
        assert is_agency(a)


def test_dictionary_size():
    assert len(AGENCIES) >= 50
