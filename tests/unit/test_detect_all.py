from ko_pii.detect import detect_all


def test_runs_all_detectors_on_mixed_text():
    text = (
        "신청인 880101-1234568, 연락처 010-1234-5678, "
        "이메일 user@example.com, IP 192.168.0.1"
    )
    detections = detect_all(text)
    labels = {d.label for d in detections}
    assert {"RRN", "PHONE", "EMAIL", "IP"}.issubset(labels)


def test_no_overlaps_in_output():
    text = "주민번호 880101-1234568"
    detections = detect_all(text)
    sorted_ds = sorted(detections, key=lambda d: d.start)
    for a, b in zip(sorted_ds, sorted_ds[1:]):
        assert a.end <= b.start


def test_include_filter():
    text = "신청인 880101-1234568 연락처 010-1234-5678"
    detections = detect_all(text, include=["RRN"])
    assert {d.label for d in detections} == {"RRN"}


def test_exclude_filter():
    text = "신청인 880101-1234568 연락처 010-1234-5678"
    detections = detect_all(text, exclude=["RRN"])
    assert "RRN" not in {d.label for d in detections}


def test_corp_reg_vs_rrn_partition():
    # 880101-1234568 → RRN takes precedence over CORP_REG anyway by virtue
    # of the corp_reg module deferring to RRN. Make sure detect_all yields
    # only RRN here.
    detections = detect_all("880101-1234568")
    labels = {d.label for d in detections}
    assert "RRN" in labels
    assert "CORP_REG" not in labels


class TestUnicodeEvasion:
    """전각/제로폭 우회 차단 (기본 normalize=True) + offset 원본 보존."""

    def test_fullwidth_phone(self):
        # 전각 숫자로 쓴 전화번호도 검출
        text = "연락처 ０１０-１２３４-５６７８ 입니다"
        ds = detect_all(text)
        phone = [d for d in ds if d.label == "PHONE"]
        assert phone, "전각 전화번호 미검출 (우회됨)"
        # offset 은 원본(전각) 위치를 가리켜야 redaction 이 올바른 글자를 지움
        d = phone[0]
        assert text[d.start:d.end] == d.text
        assert "０" in d.text  # 원본 전각 문자

    def test_zero_width_inserted_rrn(self):
        # 주민번호 중간에 제로폭 공백(U+200B) 삽입
        text = "주민등록번호 900101-1​234567"
        ds = detect_all(text)
        assert any(d.label == "RRN" for d in ds), "제로폭 삽입 RRN 미검출 (우회됨)"

    def test_fullwidth_card_checksum(self):
        # Luhn 유효 카드의 전각 버전 — 정규화 후 체크섬 통과해야 검출
        text = "카드 ４５３９-１４８８-０３４３-６４６７"
        assert any(d.label == "CARD" for d in detect_all(text))

    def test_clean_text_unchanged(self):
        # 정상 입력은 normalize on/off 결과가 동일 (회귀 없음)
        text = "서울 강남구 테헤란로 152, 010-1234-5678, user@example.com"
        on = [(d.label, d.start, d.end) for d in detect_all(text, normalize=True)]
        off = [(d.label, d.start, d.end) for d in detect_all(text, normalize=False)]
        assert on == off

    def test_normalize_false_disables(self):
        # 명시적으로 끄면 전각 우회가 통과(검출 안 됨) — 플래그 동작 확인
        text = "연락처 ０１０-１２３４-５６７８"
        assert not any(d.label == "PHONE" for d in detect_all(text, normalize=False))
