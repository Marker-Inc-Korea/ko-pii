from ko_pii.dictionaries.field_labels import (
    FIELD_LABELS,
    is_field_label,
    is_name_field_label,
)


def test_name_labels():
    for lbl in ("성명", "이름", "신청인", "민원인"):
        assert is_field_label(lbl)
        assert is_name_field_label(lbl)


def test_aux_labels_recognized_but_not_name_labels():
    for lbl in ("직책", "소속", "연락처"):
        assert is_field_label(lbl)
        assert not is_name_field_label(lbl)


def test_unknown():
    assert not is_field_label("아무튼")


def test_dictionary_size():
    assert len(FIELD_LABELS) >= 25
