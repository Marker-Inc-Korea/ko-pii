from ko_pii.modes.partial import mask_value, partial
from ko_pii.patterns.rrn import detect as detect_rrn
from ko_pii.patterns.phone import detect as detect_phone


class TestMaskValueDirect:
    def test_rrn(self):
        assert mask_value("RRN", "880101-1234568") == "880101-1******"

    def test_rrn_no_hyphen(self):
        assert mask_value("RRN", "8801011234568") == "8801011******"

    def test_phone(self):
        assert mask_value("PHONE", "010-1234-5678") == "010-****-5678"

    def test_phone_no_separator(self):
        assert mask_value("PHONE", "01012345678") == "010****5678"

    def test_email(self):
        assert mask_value("EMAIL", "user@example.com") == "u***@example.com"
        assert mask_value("EMAIL", "a@b.c") == "a***@b.c"

    def test_card(self):
        assert mask_value("CARD", "1234-5678-9012-3456") == "1234-****-****-3456"

    def test_name_korean(self):
        assert mask_value("PERSON", "홍길동") == "홍OO"
        assert mask_value("PERSON", "남궁민수") == "남궁OO"  # 복성 2자

    def test_passport(self):
        assert mask_value("PASSPORT", "M12345678") == "M******78"

    def test_account(self):
        assert mask_value("ACCOUNT", "1234567890123") == "1234*****0123"

    def test_default_fallback(self):
        # 알려지지 않은 라벨 → 양 끝 2자 노출
        assert mask_value("UNKNOWN", "abcdef") == "ab**ef"


class TestPartialInDocument:
    def test_apply_to_text_rrn(self):
        text = "신청인 주민번호: 880101-1234568"
        out = partial(text, detect_rrn(text))
        assert "880101-1******" in out
        assert "1234568" not in out

    def test_phone_in_context(self):
        text = "연락처: 010-1234-5678"
        out = partial(text, detect_phone(text))
        assert "010-****-5678" in out
