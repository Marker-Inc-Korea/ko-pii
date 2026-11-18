"""Preserve aliases and precedence captured from the published 1.25.0 wheel."""
import json
from pathlib import Path

from ko_pii.dictionaries.table_headers import TABLE_HEADER_MAP
from ko_pii.tabular import map_columns


PREVIOUS = json.loads((Path(__file__).parent / "fixtures/table_headers_1_25_0.json").read_text(encoding="utf-8"))["aliases"]


def test_previous_header_aliases_remain_in_the_same_legacy_precedence_order():
    assert [list(item) for item in TABLE_HEADER_MAP.items()][:len(PREVIOUS)] == PREVIOUS


def test_previous_exact_aliases_still_map_under_both_policies():
    expected = dict(PREVIOUS)
    assert map_columns(expected) == expected
    assert map_columns(expected, header_policy="legacy") == expected


def test_new_birth_aliases_do_not_override_existing_legacy_substring_matches():
    assert map_columns(["생년월일 이메일", "생년월일 전화번호"], header_policy="legacy") == {
        "생년월일 이메일": "EMAIL", "생년월일 전화번호": "PHONE",
    }
