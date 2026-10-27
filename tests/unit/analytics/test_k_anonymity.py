import pytest

from ko_pii.analytics.k_anonymity import k_anonymity, evaluate_dataset


class TestKAnonymityBasic:
    def test_all_identical_records_max_k(self):
        records = [
            {"PERSON": "P1", "ADDRESS": "서울"},
            {"PERSON": "P1", "ADDRESS": "서울"},
            {"PERSON": "P1", "ADDRESS": "서울"},
        ]
        rpt = k_anonymity(records)
        assert rpt.k == 3
        assert rpt.group_count == 1
        assert rpt.satisfies_threshold is False  # default threshold 5

    def test_all_unique_records_k1(self):
        records = [
            {"PERSON": "P1", "ADDRESS": "A"},
            {"PERSON": "P2", "ADDRESS": "B"},
            {"PERSON": "P3", "ADDRESS": "C"},
        ]
        rpt = k_anonymity(records)
        assert rpt.k == 1
        assert rpt.group_count == 3

    def test_satisfies_threshold(self):
        records = [{"PERSON": "P1", "ADDRESS": "서울"}] * 5
        rpt = k_anonymity(records, threshold=5)
        assert rpt.satisfies_threshold is True

    def test_below_threshold(self):
        records = [{"PERSON": "P1", "ADDRESS": "서울"}] * 3
        rpt = k_anonymity(records, threshold=5)
        assert rpt.satisfies_threshold is False
        assert any("일반화" in r for r in rpt.rationale)


class TestQuasiAutoDetection:
    def test_auto_picks_quasi_only(self):
        # RRN 은 identifier, URL 은 general — quasi 만 그룹화에 사용
        records = [
            {"RRN": "880101-1", "PERSON": "P1", "ADDRESS": "서울", "URL": "x"},
            {"RRN": "950101-2", "PERSON": "P1", "ADDRESS": "서울", "URL": "y"},
        ]
        rpt = evaluate_dataset(records)
        # 준식별자가 P1/서울 로 동일 → k=2 그룹 1개
        assert rpt.k == 2
        assert "PERSON" in rpt.quasi_identifier_keys
        assert "ADDRESS" in rpt.quasi_identifier_keys
        assert "RRN" not in rpt.quasi_identifier_keys

    def test_empty_records(self):
        rpt = k_anonymity([])
        assert rpt.k == 0
        assert rpt.record_count == 0
        assert rpt.satisfies_threshold is False

    def test_no_quasi_keys_is_not_evaluated(self):
        records = [{"RRN": "880101-1"}, {"RRN": "950101-2"}]
        rpt = k_anonymity(records)
        assert rpt.k == rpt.group_count == rpt.smallest_group_size == 0
        assert rpt.record_count == 2
        assert rpt.satisfies_threshold is False
        assert any("평가하지 않음" in r for r in rpt.rationale)


class TestKAnonymityExplicitKeys:
    def test_explicit_quasi_keys(self):
        records = [
            {"PERSON": "P1", "ADDRESS": "서울", "PHONE": "010"},
            {"PERSON": "P1", "ADDRESS": "서울", "PHONE": "011"},
        ]
        # ADDRESS 만 키로 사용
        rpt = k_anonymity(records, quasi_keys=["ADDRESS"])
        assert rpt.k == 2
        assert rpt.quasi_identifier_keys == ["ADDRESS"]


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5, "5", None, float("nan")])
def test_invalid_threshold_is_rejected_even_for_empty_data(threshold):
    with pytest.raises(ValueError, match="threshold"):
        k_anonymity([], threshold=threshold)


@pytest.mark.parametrize("keys", ["AGE", [""], [None], [["AGE"]], ["AGE", "AGE"]])
def test_invalid_key_configuration_is_rejected(keys):
    with pytest.raises(ValueError, match="quasi_keys"):
        k_anonymity([], quasi_keys=keys)


@pytest.mark.parametrize("records,keys", [
    ([{"AGE": age} for age in range(5)], ["age"]),
    ([{"AGE": 20}, {}], ["AGE"]),
    ([{"AGE": 20}, {}], None),
])
def test_missing_column_does_not_become_a_shared_null_group(records, keys):
    with pytest.raises(ValueError, match="present in every record"):
        k_anonymity(records, quasi_keys=keys)


def test_explicit_null_values_and_unique_values_are_distinct():
    assert k_anonymity([{"AGE": None}] * 5, quasi_keys=["AGE"]).k == 5
    report = k_anonymity([{"AGE": age} for age in range(5)], quasi_keys=["AGE"])
    assert report.k == 1 and not report.satisfies_threshold


def test_empty_explicit_keys_cannot_claim_threshold_pass():
    report = k_anonymity([{"AGE": 20}] * 10, quasi_keys=[], threshold=5)
    assert report.k == 0 and not report.satisfies_threshold


def test_unhashable_value_error_does_not_echo_data():
    with pytest.raises(ValueError, match="hashable") as exc:
        k_anonymity([{"AGE": ["private-value"]}])
    assert "private-value" not in str(exc.value)
