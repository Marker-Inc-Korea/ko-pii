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

    def test_no_quasi_keys_trivially_satisfies(self):
        # 준식별자가 없으면 k-익명성은 vacuously satisfied
        records = [{"RRN": "880101-1"}, {"RRN": "950101-2"}]
        rpt = k_anonymity(records)
        assert rpt.k == 2
        # 식별자만으로는 k-익명성 자체를 정의 못 함 — vacuous truth
        assert rpt.satisfies_threshold is True
        assert any("준식별자가 없어" in r for r in rpt.rationale)


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
