import unicodedata

from ko_pii import Anonymizer, ProcessingMode
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


class TestOverlapLeaks:
    """겹침 해소가 낮은 우선순위 span 으로 고신뢰 PII 를 삼켜 누출하던 회귀 방지."""

    def test_phone_after_jibun_address_not_swallowed(self):
        # 지번주소 직후 전화번호 — 주소 regex 가 전화 앞자리를 삼키면 안 됨
        t = "주소: 서울특별시 강남구 역삼동 010-9876-5432"
        phone = [d for d in detect_all(t) if d.label == "PHONE"]
        assert phone and phone[0].text == "010-9876-5432"

    def test_balanced_mode_masks_phone_after_address(self):
        # BALANCED(기본)에서 전화번호가 평문으로 새지 않아야 함
        t = "주소: 서울특별시 강남구 역삼동 010-9876-5432"
        out = Anonymizer(mode=ProcessingMode.BALANCED).process(t).text
        assert "010-9876-5432" not in out
        assert "<PHONE" in out

    def test_url_embedded_rrn_and_email_detected(self):
        # URL(INFO) 이 내부 RRN/EMAIL 을 삼켜 마스킹 누락되면 안 됨
        t = "참고 http://x.com/u?ssn=900101-1234567&m=a@b.com 끝"
        labels = {d.label for d in detect_all(t)}
        assert "RRN" in labels and "EMAIL" in labels

    def test_jibun_with_real_lot_number_keeps_both(self):
        # 진짜 번지 + 전화 — 주소와 전화 모두 보존
        t = "서울특별시 강남구 역삼동 123-45 010-9876-5432"
        labels = {d.label for d in detect_all(t)}
        assert "PHONE" in labels and "ADDRESS" in labels


class TestNfdEvasion:
    """NFD(분해형) 한글로 검출을 우회하던 문제 회귀 방지."""

    def test_nfd_name_and_rrn_detected(self):
        nfc = "홍길동 900101-1234567"
        nfd = unicodedata.normalize("NFD", nfc)
        assert nfd != nfc  # 실제로 분해됐는지 확인
        labels = {d.label for d in detect_all(nfd)}
        assert "PERSON" in labels and "RRN" in labels

    def test_nfd_offset_invariant(self):
        nfd = unicodedata.normalize("NFD", "홍길동 900101-1234567")
        for d in detect_all(nfd):
            assert nfd[d.start:d.end] == d.text


class TestCorpRegPipeline:
    """detect_all 파이프라인 수준에서 법인번호가 RRN 으로 오라벨되지 않아야 함 (D-003)."""

    def test_corp_number_labeled_corp_reg(self):
        # 삼성전자 130111-0006246 — 법인 체크섬 통과, RRN 아님
        ds = detect_all("법인등록번호 130111-0006246")
        labels = {d.label for d in ds}
        assert "CORP_REG" in labels and "RRN" not in labels

    def test_real_rrn_not_stolen_by_corp(self):
        # 실제 RRN 은 법인 체크섬을 우연히 통과해도 RRN 으로 보호
        ds = detect_all("880101-1234568")
        labels = {d.label for d in ds}
        assert "RRN" in labels and "CORP_REG" not in labels


def test_zwsp_separated_pii_still_detected() -> None:
    # 제로폭으로 끼워넣은/쪼갠 PII 도 정규화 + (필요시) 원본 재검사로 검출 유지.
    from ko_pii import detect_all
    zw = "​"
    assert any(d.label == "PHONE" for d in detect_all(f"연락처 010{zw}1234{zw}5678"))
    assert any(d.label == "RRN" for d in detect_all(f"주민 900101{zw}1234567"))
