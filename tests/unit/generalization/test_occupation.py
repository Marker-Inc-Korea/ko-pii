from ko_pii.generalization.occupation import generalize_occupation


def test_civil_servant_category():
    assert generalize_occupation("기획재정부 과장") == "공무원"
    assert generalize_occupation("주무관") == "공무원"


def test_medical_category():
    assert generalize_occupation("내과 의사") == "의료"


def test_legal_category():
    assert generalize_occupation("부장판사") == "법조"


def test_unknown_passthrough():
    assert generalize_occupation("게임 디자이너") == "게임 디자이너"
