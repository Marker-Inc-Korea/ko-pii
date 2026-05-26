import pytest

from ko_pii.generalization.age import generalize_age


def test_basic_bucketing():
    assert generalize_age(34) == "30대"
    assert generalize_age(20) == "20대"
    assert generalize_age(29) == "20대"
    assert generalize_age(0) == "0대"
    assert generalize_age(95) == "90대"


def test_custom_bucket_size():
    assert generalize_age(34, bucket_size=5) == "30대"
    assert generalize_age(38, bucket_size=5) == "35대"


def test_invalid_inputs():
    with pytest.raises(ValueError):
        generalize_age(-1)
    with pytest.raises(ValueError):
        generalize_age(20, bucket_size=0)
