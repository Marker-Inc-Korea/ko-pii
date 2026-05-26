from datetime import date

import pytest

from ko_pii.generalization.date import generalize_date


def test_year_precision():
    assert generalize_date(date(1988, 1, 15)) == "1988년"


def test_month_precision():
    assert generalize_date(date(1988, 1, 15), precision="month") == "1988-01"


def test_decade_precision():
    assert generalize_date(date(1988, 1, 15), precision="decade") == "1980년대"
    assert generalize_date(date(2024, 6, 1), precision="decade") == "2020년대"


def test_unknown_precision():
    with pytest.raises(ValueError):
        generalize_date(date(1988, 1, 1), precision="century")
