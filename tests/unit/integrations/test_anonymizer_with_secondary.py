from ko_pii import Anonymizer, MockSecondaryDetector, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel


def _det(label, start, end, text):
    return DetectionResult(
        label=label, text=text, start=start, end=end,
        risk_level=RiskLevel.HIGH, confidence=0.85,
        evidence=[f"source:mock"],
    )


class TestAnonymizerWithSecondary:
    def test_no_secondary_works_as_before(self):
        """Secondary 없으면 기존 동작 동일."""
        anon = Anonymizer(mode=ProcessingMode.STRICT)
        result = anon.process("주민번호 880101-1234568")
        assert "880101-1234568" not in result.text

    def test_secondary_complements_primary(self):
        """Secondary 가 primary 가 놓친 부분 catch."""
        text = "이상한이름 880101-1234568"  # "이상한이름" — ko-pii 가 못 잡을 가능성

        # Mock 이 "이상한이름" 을 PERSON 으로 라벨
        mock = MockSecondaryDetector([
            _det("PERSON", 0, 5, "이상한이름"),
        ])
        anon = Anonymizer(
            mode=ProcessingMode.STRICT,
            strategy="redact",
            secondary_detector=mock,
            merge_mode="union",
        )
        result = anon.process(text)
        # ko-pii 가 RRN 잡고, mock 이 이름 잡음
        assert "[주민등록번호]" in result.text
        assert "[성명]" in result.text

    def test_intersection_mode_strict(self):
        """양쪽 다 잡은 것만 인정 (high confidence)."""
        text = "신청인 홍길동 880101-1234568"
        # Mock: 홍길동을 PERSON 으로 잡음 (ko-pii 도 잡음)
        mock = MockSecondaryDetector([
            _det("PERSON", 4, 7, "홍길동"),
        ])
        anon = Anonymizer(
            mode=ProcessingMode.STRICT,
            strategy="tokenize",
            secondary_detector=mock,
            merge_mode="intersection",
        )
        result = anon.process(text)
        # 양쪽 모두 잡은 PERSON 은 corroboration 부착
        person_recs = [r for r in result.detections if r.detection.label == "PERSON"]
        if person_recs:
            evidence = " ".join(person_recs[0].detection.evidence)
            assert "corroborated_by" in evidence

    def test_cross_validation_uncorroborated(self):
        """ko-pii 가 못 잡은 secondary 만의 검출은 신뢰도 낮음."""
        text = "John Smith 880101-1234568"
        mock = MockSecondaryDetector([
            _det("PERSON", 0, 10, "John Smith"),  # 영문 이름
        ])
        anon = Anonymizer(
            mode=ProcessingMode.STRICT,
            strategy="redact",
            secondary_detector=mock,
            merge_mode="cross_validation",
        )
        result = anon.process(text)
        # uncorroborated 라 confidence 페널티
        person_recs = [r for r in result.detections if r.detection.label == "PERSON"]
        if person_recs:
            assert person_recs[0].detection.confidence < 0.7

    def test_secondary_respects_include_filter(self):
        """include 필터가 secondary 에도 적용."""
        mock = MockSecondaryDetector([
            _det("PERSON", 0, 3, "AAA"),
            _det("EMAIL", 5, 15, "a@b.com"),
        ])
        anon = Anonymizer(
            mode=ProcessingMode.STRICT,
            strategy="redact",
            secondary_detector=mock,
            include=["PERSON"],  # EMAIL 제외
        )
        result = anon.process("AAA, a@b.com 입니다")
        # PERSON 은 가명화, EMAIL 은 그대로
        assert "AAA" not in result.text
        assert "a@b.com" in result.text


class TestProtocol:
    def test_mock_implements_protocol(self):
        from ko_pii.integrations.base import SecondaryDetector
        mock = MockSecondaryDetector([])
        assert isinstance(mock, SecondaryDetector)
