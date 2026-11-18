"""Address details remain PII after commas, parentheses and wrapped lines."""
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault
from ko_pii.patterns.address import detect


BASE = "서울특별시 강남구 테헤란로 152"
DETAILS = [
    ", 101동 1202호", ",101동,1202호", ", 12층, 1202호",
    " (역삼동) 101동 1202호", ", (역삼동) 101동, 1202호",
    " (역삼동, 예시타워) 12층", ", 예시타워, 12층",
    ", 예시타워 (역삼동) 12층 1202호",
    ", 예시타워\n101동 1202호",
]


@pytest.mark.parametrize("detail", DETAILS)
@pytest.mark.parametrize("form", ["NFC", "NFD"])
@pytest.mark.parametrize("strategy", ["redact", "tokenize", "asterisk"])
def test_address_detail_is_part_of_the_single_replaced_source_span(detail, form, strategy):
    raw = unicodedata.normalize(form, BASE + detail)
    source = "주소: " + raw + "; 연락처: 010-1234-5678"
    engine = Anonymizer(mode=ProcessingMode.STRICT, strategy=strategy, include=["ADDRESS"])
    result = engine.process(source)
    assert len(result.detections) == 1
    detection = result.detections[0].detection
    assert (detection.start, detection.end, detection.text) == (4, 4 + len(raw), raw)
    assert result.text.startswith("주소: ") and result.text.endswith("; 연락처: 010-1234-5678")
    assert "1202" not in result.text and "101동" not in result.text
    if strategy == "tokenize":
        assert engine.vault.reveal("<ADDRESS_1>") == raw


@pytest.mark.parametrize("road", ["봉은사로 1길", "봉은사로 1번길", "봉은사로1길"])
def test_alley_number_is_not_mistaken_for_the_building_number(road):
    address = "서울특별시 강남구 " + road + " 10"
    found = list(detect(address))
    assert len(found) == 1
    assert found[0].text == address
    assert found[0].extra["building_number"] == "10"
    assert Anonymizer(include=["ADDRESS"], strategy="redact").process("주소: " + address).text == "주소: [주소]"


@pytest.mark.parametrize("tail", [", 연락처: 010-1234-5678", ", 금액: 100000원", ", 다음 문장입니다."])
def test_comma_is_only_consumed_when_it_leads_to_address_detail(tail):
    source = BASE + tail
    assert [d.text for d in detect(source)] == [BASE]


def test_unknown_building_bridge_does_not_cross_into_another_text_record():
    source = BASE + "\n김다은 12층"
    assert [d.text for d in detect(source)] == [BASE]


def test_adjacent_person_and_phone_are_not_swallowed_or_displace_the_address():
    source = "주소: " + BASE + ", 101동, 1202호\n성명: 김다은\n전화: 010-1234-5678"
    engine = Anonymizer()
    result = engine.process(source)
    assert result.text == "주소: <ADDRESS_1>\n성명: <PERSON_1>\n전화: <PHONE_1>"
    saved = ReversibleVault.from_dict(engine.vault.to_dict())
    assert saved.reveal("<ADDRESS_1>") == BASE + ", 101동, 1202호"
