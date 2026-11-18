"""Do not confuse adjacent fields, word fragments, and connected digit groups."""
import json
import unicodedata

import pytest

from ko_pii import Anonymizer, ProcessingMode, ReversibleVault, anonymize_json, detect_all
from ko_pii.cli import main
from ko_pii.patterns import account, card


ACCOUNT = "110-123-456789"
VISA = "4111-1111-1111-1111"


@pytest.mark.parametrize("prefix,suffix", [
    ("계좌번호=", ""), ("계좌 번호 = ", ""), ('계좌번호: "', '"'),
    ("계좌번호: '", "'"), ("계좌번호: “", "”"), ("계좌번호: ‘", "’"),
    ("계좌번호: 「", "」"), ("계좌번호: 『", "』"), ("계좌번호: (", ")"),
    ('신한은행 = "', '"'), ("", ", 신한은행"), ('"', '", 신한은행'),
    ("(", ") 신한은행"),
])
@pytest.mark.parametrize("variant", ["plain", "fullwidth", "invisible", "nfd"])
def test_account_field_punctuation_keeps_the_exact_numeric_source_span(prefix, suffix, variant):
    raw = ACCOUNT
    if variant == "fullwidth":
        raw = "".join(chr(ord(ch) + 0xFEE0) for ch in raw)
    elif variant == "invisible":
        raw = raw[:2] + "\u200b" + raw[2:]
    elif variant == "nfd":
        prefix = unicodedata.normalize("NFD", prefix)
        suffix = unicodedata.normalize("NFD", suffix)
    source = prefix + raw + suffix
    result = Anonymizer(strategy="redact", include=["ACCOUNT"]).process(source)
    assert result.text == prefix + "[계좌번호]" + suffix
    assert [(r.detection.text, r.detection.start, r.detection.end) for r in result.detections] == [
        (raw, len(prefix), len(prefix) + len(raw)),
    ]


@pytest.mark.parametrize("word", ["리스트하나", "주소는우리", "구신한", "USERNH", "XIBK", "éNH", "漢NH", "_KB"])
def test_bank_before_value_cannot_start_inside_another_word(word):
    source = word + " " + ACCOUNT
    assert list(account.detect(source)) == []
    assert Anonymizer(include=["ACCOUNT"], strategy="redact").process(source).text == source


@pytest.mark.parametrize("word", ["우리동네", "하나뿐인", "신한제품", "NHasset", "KB2", "NHé", "NH漢", "NH_"])
def test_bank_after_value_cannot_end_inside_another_word(word):
    source = ACCOUNT + " " + word
    assert list(account.detect(source)) == []
    assert detect_all(source, include=["ACCOUNT"]) == []


@pytest.mark.parametrize("bank", [
    "신한은행", "NH농협은행", "IBK기업은행", "KDB산업은행", "BNK부산은행", "BNK경남은행",
    "DGB대구은행", "Sh수협은행", "JB제주은행", "국민", "NH", "KB",
])
@pytest.mark.parametrize("placement", ["before", "after"])
def test_existing_qualified_and_short_bank_anchors_remain_supported(bank, placement):
    source = bank + " " + ACCOUNT if placement == "before" else ACCOUNT + " " + bank
    found = list(account.detect(source))
    assert len(found) == 1 and found[0].text == ACCOUNT
    assert found[0].extra["bank"] == bank


@pytest.mark.parametrize("ending", ["은", "에서", "으로", "으로는", "으로부터", "으로부터만", "으로부터의", "에서도", "까지", "입니다", "이며"])
def test_bank_after_account_keeps_bounded_korean_particles_outside_the_value(ending):
    source = ACCOUNT + " 신한은행" + ending + " 확인했습니다."
    assert Anonymizer(strategy="redact", include=["ACCOUNT"]).process(source).text == "[계좌번호] 신한은행" + ending + " 확인했습니다."


@pytest.mark.parametrize("bank", ["신한은행", "NH농협은행", "토스뱅크", "카카오뱅크"])
@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_full_bank_names_after_compact_korean_prose_are_not_lost(bank, form):
    prefix = unicodedata.normalize(form, "입금은" + bank)
    source = prefix + ACCOUNT
    assert Anonymizer(strategy="redact", include=["ACCOUNT"]).process(source).text == prefix + "[계좌번호]"


@pytest.mark.parametrize("separator", ["-", ".", "/", " ", "  ", "- ", "-\n", "-\r\n"])
@pytest.mark.parametrize("side", ["before", "after"])
def test_unsupported_connected_groups_are_not_sliced_to_a_valid_card(separator, side):
    groups = ["4111", "1111", "1111", "1111"]
    groups = ["1234", *groups] if side == "before" else [*groups, "1234"]
    source = separator.join(groups)
    assert list(card.detect(source)) == []
    assert detect_all(source, include=["CARD"]) == []
    assert Anonymizer(strategy="redact", include=["CARD"]).process(source).text == source


@pytest.mark.parametrize("prefix,suffix", [
    ("01012345678 ", ""), ("110123456789 ", ""), ("2026: ", ""),
    ("", " 5555555555554444"), ("", "\n1234"), ("", ", 금액 100000"),
])
def test_complete_neighboring_fields_are_not_joined_to_a_card(prefix, suffix):
    source = prefix + VISA + suffix
    found = list(card.detect(source))
    assert any(d.text == VISA and d.start == len(prefix) for d in found)


def test_two_complete_bare_cards_remain_separate():
    source = "4111111111111111 5555555555554444"
    assert [d.text for d in card.detect(source)] == source.split()
    assert [d.text for d in card.detect("2026 " + source)] == source.split()


def test_punctuation_and_alias_boundaries_through_json_cli_and_saved_vault(tmp_path):
    source = '계좌번호=“' + ACCOUNT + '”\n리스트하나 110-123-456789'
    engine = Anonymizer(include=["ACCOUNT"])
    masked = engine.process(source)
    expected = '계좌번호=“<ACCOUNT_1>”\n리스트하나 110-123-456789'
    assert masked.text == expected
    assert anonymize_json({"note": source}, anonymizer=Anonymizer(include=["ACCOUNT"])).data == {"note": expected}
    path, output, vault_path = (tmp_path / name for name in ("in.txt", "out.txt", "vault.json"))
    path.write_bytes(source.encode())
    assert main([str(path), "--include", "ACCOUNT", "-o", str(output), "--vault", str(vault_path)]) == 0
    assert output.read_text(encoding="utf-8") == expected
    vault = ReversibleVault.from_dict(json.loads(vault_path.read_text(encoding="utf-8")))
    assert vault.reveal("<ACCOUNT_1>") == ACCOUNT
    audit = Anonymizer(mode=ProcessingMode.AUDIT, include=["ACCOUNT"]).process(source)
    assert audit.text == source and not audit.substitutions
