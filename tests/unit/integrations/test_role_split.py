"""ROLE_SPLIT 병합 모드 + HFTokenNERAdapter bio_decode 테스트.

ROLE_SPLIT = HYBRID_NER.md 의 하이브리드(룰=결정적 ID, ML=퍼지 교체) 구성을
라이브러리 기능으로 노출한 것 — 외부 검증(F1 0.97)에서 union 을 능가한 모드.
"""
from ko_pii import Anonymizer, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.integrations import MergeMode, merge_detections
from ko_pii.integrations.base import MockSecondaryDetector
from ko_pii.integrations.hf_token_ner import bio_decode


def _det(label, start, end, text, risk=RiskLevel.MEDIUM, conf=0.8):
    return DetectionResult(label=label, text=text, start=start, end=end,
                           risk_level=risk, confidence=conf, evidence=[])


class TestRoleSplitMerge:
    def test_delegated_labels_replaced_by_secondary(self):
        # 퍼지(PERSON)는 ML 로 교체 — 룰의 PERSON 검출은 폐기
        primary = [
            _det("RRN", 10, 24, "880101-1234568", risk=RiskLevel.CRITICAL),
            _det("PERSON", 0, 2, "홍길"),          # 룰의 부정확한 퍼지 검출
        ]
        secondary = [
            _det("PERSON", 0, 3, "홍길동", risk=RiskLevel.HIGH),
            _det("ADDRESS", 30, 40, "서울시 강남구"),
        ]
        out = merge_detections(primary, secondary, mode=MergeMode.ROLE_SPLIT)
        by_label = {r.label: r for r in out}
        assert by_label["RRN"].text == "880101-1234568"      # 룰 유지
        assert by_label["PERSON"].text == "홍길동"            # ML 로 교체
        assert by_label["ADDRESS"].text == "서울시 강남구"    # ML 추가
        assert len(out) == 3

    def test_secondary_non_delegated_labels_dropped(self):
        # ML 이 결정적 ID(RRN)를 내놔도 위임 라벨이 아니면 폐기 — 룰만 신뢰
        primary = [_det("RRN", 0, 14, "880101-1234568", risk=RiskLevel.CRITICAL)]
        secondary = [_det("RRN", 0, 13, "880101-123456", risk=RiskLevel.CRITICAL)]
        out = merge_detections(primary, secondary, mode=MergeMode.ROLE_SPLIT)
        assert len(out) == 1
        assert out[0].text == "880101-1234568"

    def test_custom_role_split_labels(self):
        primary = [_det("PERSON", 0, 3, "홍길동"), _det("EMAIL", 10, 17, "a@b.com")]
        secondary = [_det("EMAIL", 10, 18, "a@b.co.kr")]
        out = merge_detections(primary, secondary, mode=MergeMode.ROLE_SPLIT,
                               role_split_labels={"EMAIL"})
        by_label = {r.label: r for r in out}
        assert by_label["EMAIL"].text == "a@b.co.kr"   # 위임 라벨 → ML
        assert by_label["PERSON"].text == "홍길동"      # 비위임 → 룰 유지

    def test_no_secondary_fuzzy_means_no_fuzzy_output(self):
        # 교체 모드의 의미: ML 이 못 잡으면 룰 퍼지로 메꾸지 않는다 (union 과 구분)
        primary = [_det("PERSON", 0, 3, "홍길동")]
        out = merge_detections(primary, [], mode=MergeMode.ROLE_SPLIT)
        assert out == []


class TestRoleSplitAnonymizer:
    def test_end_to_end_masking(self):
        text = "신청인 홍길동 주민등록번호 880101-1234568"
        ml = MockSecondaryDetector([
            _det("PERSON", 4, 7, "홍길동", risk=RiskLevel.HIGH, conf=0.95),
        ])
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact",
                          secondary_detector=ml, merge_mode="role_split")
        result = anon.process(text)
        assert "[성명]" in result.text            # ML 퍼지 검출이 마스킹으로 연결
        assert "880101-1234568" not in result.text  # 룰 RRN 유지
        assert "홍길동" not in result.text

    def test_role_split_labels_passthrough(self):
        text = "신청인 홍길동 주민등록번호 880101-1234568"
        ml = MockSecondaryDetector([])  # ML 이 아무것도 못 잡는 상황
        anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact",
                          secondary_detector=ml, merge_mode="role_split",
                          role_split_labels={"ADDRESS"})  # PERSON 은 위임 안 함
        result = anon.process(text)
        assert "홍길동" not in result.text  # PERSON 비위임 → 룰 검출 유지


class TestBioDecode:
    TEXT = "신청인 홍길동 연락처"
    #       0123456789

    def test_basic_b_i_span(self):
        offsets = [(0, 0), (0, 3), (4, 5), (5, 7), (8, 11), (0, 0)]
        tags = ["O", "O", "B-PERSON", "I-PERSON", "O", "O"]
        out = bio_decode(self.TEXT, offsets, tags)
        assert len(out) == 1
        assert out[0].label == "PERSON"
        assert out[0].text == "홍길동"
        assert (out[0].start, out[0].end) == (4, 7)

    def test_label_change_without_b_starts_new_span(self):
        offsets = [(0, 3), (4, 7)]
        tags = ["I-ADDRESS", "I-PERSON"]  # B 없이 라벨 변경 — 각각 별도 span
        out = bio_decode(self.TEXT, offsets, tags)
        assert [r.label for r in out] == ["ADDRESS", "PERSON"]

    def test_special_tokens_ignored_and_confidence_averaged(self):
        offsets = [(0, 0), (4, 5), (5, 7)]
        tags = ["B-PERSON", "B-PERSON", "I-PERSON"]  # (0,0) 스페셜은 무시
        out = bio_decode(self.TEXT, offsets, tags, confidences=[0.1, 0.8, 1.0])
        assert len(out) == 1
        assert abs(out[0].confidence - 0.9) < 1e-9  # (0.8+1.0)/2 — 스페셜 제외

    def test_short_person_filtered(self):
        offsets = [(4, 5)]
        tags = ["B-PERSON"]
        assert bio_decode(self.TEXT, offsets, tags) == []  # 1자 PERSON 제외

    def test_risk_level_mapping(self):
        offsets = [(4, 7)]
        out = bio_decode(self.TEXT, offsets, ["B-PERSON"])
        assert out[0].risk_level == RiskLevel.HIGH
