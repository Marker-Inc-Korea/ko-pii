import pytest

from ko_pii.patterns.phone import detect


@pytest.mark.parametrize("prefix", ["010", "011", "016", "017", "018", "019"])
@pytest.mark.parametrize("separator", ["-", ".", " ", "", " - "])
@pytest.mark.parametrize("middle", ["234", "2345"])
@pytest.mark.parametrize("notation", ["domestic", "parenthesized", "+82", "0082"])
def test_mobile_prefix_format_matrix(prefix, separator, middle, notation):
    if notation == "parenthesized":
        area = f"({prefix})"
    elif notation in ("+82", "0082"):
        area = notation + "-" + prefix[1:]
    else:
        area = prefix
    value = separator.join([area, middle, "6789"])
    text = f"Tel: {value}; end"
    results = list(detect(text))
    assert len(results) == 1
    found = results[0]
    assert (found.text, found.start, found.end) == (value, 5, 5 + len(value))
    assert found.extra["type"] == "mobile"
    assert found.extra["international"] == (notation in ("+82", "0082"))


@pytest.mark.parametrize("text", [
    "012-2345-6789", "013-2345-6789", "014-2345-6789", "015-2345-6789",
    "9018-2345-6789", "018-2345-67890", "(018) 2345-67890", "+82-18-2345-67890",
])
def test_numeric_boundaries_and_unsupported_prefixes(text):
    assert not list(detect(text))
