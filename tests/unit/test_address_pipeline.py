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


@pytest.mark.parametrize("detail", [
    " B1층", " b2층 B101호", " 지하1층", " 지하 1층 101호실", " 지상 2층",
    " A동101호", " A동 지하1층 101호실", " 가동101호", " 101동1202호",
    " 101동/1202호", " 101동-1202호", " B101호실",
])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_typed_building_and_basement_units_are_fully_protected(detail, form):
    canonical = BASE + detail
    assert [item.text for item in detect(canonical)] == [canonical]
    raw = unicodedata.normalize(form, canonical)
    source = "주소: " + raw + "에서 접수; 전화: 010-1234-5678"
    vault = ReversibleVault(salt="address-units", secret_key="test", fingerprint_iterations=1)
    result = Anonymizer(vault=vault).process(source)
    assert result.text == "주소: <ADDRESS_1>에서 접수; 전화: <PHONE_1>"
    assert vault.reveal("<ADDRESS_1>") == raw


@pytest.mark.parametrize("tail", [
    " 3호선으로 이동", " 101동작 시험", " A동작은 오류", " 가동률 상승", " 10층수 통계",
    " 101호실적 증가", " 101동네 방문", " 12층위 분류",
])
def test_unit_prefix_inside_an_ordinary_word_is_not_an_address_detail(tail):
    assert [item.text for item in detect(BASE + tail)] == [BASE]
    assert Anonymizer(include=["ADDRESS"], strategy="redact").process(BASE + tail).text == "[주소]" + tail


@pytest.mark.parametrize("unit", ["101동", "1202호", "12층", "B1층", "101호실"])
@pytest.mark.parametrize("tail", [
    "근처에서 만나요.", "앞에서 기다립니다.", "로비에서 접수합니다.",
    "내부로 이동", "에서만나요", "앞에서기다립니다", "옆상가로 이동", "맞은편입니다.",
    "입니다.", "이라고 했습니다.", "이며 방문 예정입니다.",
])
def test_joined_location_phrases_do_not_leave_previously_protected_unit_numbers(unit, tail):
    address = BASE + " " + unit
    source = "주소: " + address + tail
    # Location prose is not part of the address, and must not disappear with it.
    assert [item.text for item in detect(source)] == [address]
    result = Anonymizer(include=["ADDRESS"], strategy="redact").process(source)
    assert result.text == "주소: [주소]" + tail


@pytest.mark.parametrize("tail", [" 101동내역 확인", " 101동앞선 기록", " 1202호선택", " 12층로비스트"])
def test_location_noun_prefixes_inside_other_words_are_not_continuations(tail):
    assert [item.text for item in detect(BASE + tail)] == [BASE]


@pytest.mark.parametrize("unit", ["101호", "101호실", "12층", "지하1층"])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_joined_unit_and_location_keep_vault_boundaries_in_the_full_pipeline(unit, form):
    raw = unicodedata.normalize(form, BASE + " " + unit)
    suffix = unicodedata.normalize(form, "앞에서 접수; 전화: ")
    source = "주소: " + raw + suffix + "010-1234-5678"
    vault = ReversibleVault(salt="unit-tails", secret_key="test", fingerprint_iterations=1)
    result = Anonymizer(vault=vault).process(source)
    assert result.text == "주소: <ADDRESS_1>" + suffix + "<PHONE_1>"
    assert vault.reveal("<ADDRESS_1>") == raw


@pytest.mark.parametrize("ending", ["", "의 담당자"])
def test_markdown_underscores_are_outside_the_address_unit(ending):
    source = "__" + BASE + " 101동" + ending + "__"
    assert Anonymizer(include=["ADDRESS"], strategy="redact").process(source).text == "__[주소]" + ending + "__"
