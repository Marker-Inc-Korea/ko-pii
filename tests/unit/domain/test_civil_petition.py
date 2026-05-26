from ko_pii.domain.civil_petition import detect


def _d(text):
    return list(detect(text))


class TestPetitionPositive:
    def test_minwon_format(self):
        results = _d("민원번호: 2024-민원-00123")
        assert len(results) == 1
        assert results[0].text == "2024-민원-00123"

    def test_information_disclosure(self):
        assert len(_d("청구번호: 2025-정보공개-00567")) == 1

    def test_keyword_first(self):
        assert len(_d("민원-2024-12345")) == 1

    def test_administrative_appeal(self):
        assert len(_d("행정심판-2024-00890")) == 1


class TestPetitionNegative:
    def test_random_year_dash(self):
        assert _d("2024-00123") == []

    def test_unknown_keyword(self):
        assert _d("2024-기타-00123") == []


class TestPetitionStructure:
    def test_legal_basis(self):
        r = _d("2024-민원-00123")[0]
        assert "민원처리" in r.legal_basis
