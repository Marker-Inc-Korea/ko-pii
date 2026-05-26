from ko_pii.patterns.edi_drug import detect


def _d(text):
    return list(detect(text))


class TestEdiDrugKD13:
    def test_kd13_korea_country_code(self):
        r = _d("KD코드: 8801234567890")[0]
        assert r.label == "EDI_DRUG"
        assert r.text == "8801234567890"
        assert r.extra["format"] == "kd_code_13"
        assert r.extra["country_id"] == "880"

    def test_kd13_other_korean_prefix(self):
        assert len(_d("KD코드: 8811234567890")) == 1

    def test_kd13_non_korean_rejected(self):
        assert _d("KD코드: 1234567890123") == []


class TestEdiDrug9:
    def test_basic_edi_9(self):
        r = _d("EDI 123456789")[0]
        assert r.text == "123456789"
        assert r.extra["format"] == "edi_9"
        assert r.extra["company_id"] == "1234"
        assert r.extra["item_id"] == "56789"

    def test_alternate_keywords(self):
        for kw in ("약품코드", "의약품코드", "주성분코드"):
            assert len(_d(f"{kw} 987654321")) == 1


class TestEdiDrugNegative:
    def test_no_keyword_rejected(self):
        assert _d("123456789") == []
        assert _d("8801234567890") == []
