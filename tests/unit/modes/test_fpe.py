from ko_pii.modes.fpe import fpe
from ko_pii.patterns.rrn import detect as detect_rrn
from ko_pii.patterns.phone import detect as detect_phone
from ko_pii.vault.reversible import ReversibleVault


class TestFpeFormatPreservation:
    def test_rrn_length_and_hyphen(self):
        text = "주민번호 880101-1234568"
        out, _ = fpe(text, detect_rrn(text), vault=ReversibleVault(salt="x"))
        # 원본과 길이 동일, 하이픈 위치 유지
        assert "880101-1234568" not in out
        # 새 값은 6자리-7자리 형태
        import re
        m = re.search(r"\d{6}-\d{7}", out)
        assert m is not None

    def test_rrn_passes_checksum(self):
        from ko_pii.checksum.rrn_checksum import is_valid_checksum
        text = "880101-1234568"
        out, _ = fpe(text, detect_rrn(text), vault=ReversibleVault(salt="x"))
        import re
        m = re.search(r"(\d{6})-(\d{7})", out)
        digits = m.group(1) + m.group(2)
        # FPE 후에도 체크섬이 일관성 있음 (분석 호환)
        assert is_valid_checksum(digits) is True

    def test_phone_preserves_carrier_prefix(self):
        text = "연락처 010-1234-5678"
        out, _ = fpe(text, detect_phone(text), vault=ReversibleVault(salt="x"))
        # 010 prefix 보존, 길이·하이픈 보존
        import re
        m = re.search(r"010-\d{4}-\d{4}", out)
        assert m is not None
        assert "010-1234-5678" not in out


class TestFpeDeterministic:
    def test_same_input_same_output(self):
        text = "880101-1234568"
        v1 = ReversibleVault(salt="abc")
        v2 = ReversibleVault(salt="abc")
        out1, _ = fpe(text, detect_rrn(text), vault=v1)
        out2, _ = fpe(text, detect_rrn(text), vault=v2)
        assert out1 == out2  # 같은 salt → 같은 결과 (결정적)

    def test_different_salt_different_output(self):
        text = "880101-1234568"
        a, _ = fpe(text, detect_rrn(text), vault=ReversibleVault(salt="A"))
        b, _ = fpe(text, detect_rrn(text), vault=ReversibleVault(salt="B"))
        assert a != b


class TestFpeAnonymizerIntegration:
    def test_anonymizer_fpe_strategy(self):
        from ko_pii import Anonymizer, ProcessingMode
        anon = Anonymizer(
            mode=ProcessingMode.STRICT, strategy="fpe",
            vault=ReversibleVault(salt="abc"),
        )
        result = anon.process("환자 880101-1234568 연락 010-1234-5678")
        # 원본 PII 미존재
        assert "880101-1234568" not in result.text
        assert "010-1234-5678" not in result.text
        # 형식은 유지
        import re
        assert re.search(r"\d{6}-\d{7}", result.text)
        assert re.search(r"010-\d{4}-\d{4}", result.text)
