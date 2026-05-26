"""OpenAI Privacy Filter 어댑터 — soft import + BIO 파싱 단위 테스트.

실제 모델 다운로드·실행 테스트는 [ml] extras 설치 + 큰 디스크 필요.
여기서는 import 안전성 + 라벨 매핑 + BIO 파싱 로직만 검증.
"""
import pytest


class TestSoftImport:
    def test_module_imports_without_transformers(self):
        """transformers 없어도 모듈 import 자체는 성공 — lazy load."""
        from ko_pii.integrations import openai_privacy_filter as opf
        assert hasattr(opf, "OpenAIPrivacyFilterAdapter")

    def test_get_adapter_lazy(self):
        """get_privacy_filter_adapter 는 호출 시점에만 transformers 필요."""
        from ko_pii.integrations import get_privacy_filter_adapter
        # 인스턴스 생성 자체는 transformers 없이도 가능 (lazy load)
        adapter = get_privacy_filter_adapter(device="cpu")
        assert adapter.name == "openai-privacy-filter"
        assert adapter.device == "cpu"

    def test_detect_without_transformers_raises_clear(self, monkeypatch):
        from ko_pii.integrations.openai_privacy_filter import OpenAIPrivacyFilterAdapter

        adapter = OpenAIPrivacyFilterAdapter()

        # transformers import 강제 실패
        import sys
        monkeypatch.setitem(sys.modules, "transformers", None)
        with pytest.raises((ImportError, Exception)):
            list(adapter.detect("test"))


class TestLabelMap:
    def test_known_labels_present(self):
        from ko_pii.integrations.openai_privacy_filter import _LABEL_MAP
        # 표준 PII 라벨들이 매핑됨
        assert _LABEL_MAP.get("PERSON") == "PERSON"
        assert _LABEL_MAP.get("EMAIL_ADDRESS") == "EMAIL"
        assert _LABEL_MAP.get("PHONE_NUMBER") == "PHONE"
        assert _LABEL_MAP.get("CREDIT_CARD") == "CARD"
        assert _LABEL_MAP.get("SSN") == "RRN"  # 한국 환경

    def test_non_pii_labels_mapped_to_none(self):
        from ko_pii.integrations.openai_privacy_filter import _LABEL_MAP
        # 날짜·조직·직책 등은 PII 아님
        assert _LABEL_MAP.get("DATE_TIME") is None
        assert _LABEL_MAP.get("ORGANIZATION") is None
        assert _LABEL_MAP.get("O") is None


class TestBioToSpans:
    def test_bio_aggregation(self):
        """B-PERSON / I-PERSON 시퀀스가 단일 span 으로 통합."""
        from ko_pii.integrations.openai_privacy_filter import OpenAIPrivacyFilterAdapter

        adapter = OpenAIPrivacyFilterAdapter(threshold=0.3)
        # 가상 출력 시뮬레이션
        text = "홍길동 회의"
        offsets = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6]]
        preds = [0, 1, 1, 2, 2, 2]  # B-PERSON, I-PERSON, I-PERSON, O, O, O
        scores = [0.9, 0.9, 0.9, 0.1, 0.1, 0.1]
        id2label = {0: "B-PERSON", 1: "I-PERSON", 2: "O"}

        spans = list(adapter._bio_to_spans(text, offsets, preds, scores, id2label))
        assert len(spans) == 1
        assert spans[0].label == "PERSON"
        assert spans[0].text == "홍길동"
        assert spans[0].start == 0
        assert spans[0].end == 3

    def test_threshold_filters_low_confidence(self):
        from ko_pii.integrations.openai_privacy_filter import OpenAIPrivacyFilterAdapter
        adapter = OpenAIPrivacyFilterAdapter(threshold=0.8)
        text = "홍길동"
        offsets = [[0, 1], [1, 2], [2, 3]]
        preds = [0, 1, 1]
        scores = [0.4, 0.5, 0.4]  # 모두 threshold 미만
        id2label = {0: "B-PERSON", 1: "I-PERSON"}
        spans = list(adapter._bio_to_spans(text, offsets, preds, scores, id2label))
        assert spans == []

    def test_multiple_entities(self):
        from ko_pii.integrations.openai_privacy_filter import OpenAIPrivacyFilterAdapter
        adapter = OpenAIPrivacyFilterAdapter(threshold=0.3)
        text = "홍길동과 김민수"
        offsets = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 8]]
        preds = [0, 1, 1, 2, 2, 0, 1, 1]
        scores = [0.9] * 8
        id2label = {0: "B-PERSON", 1: "I-PERSON", 2: "O"}
        spans = list(adapter._bio_to_spans(text, offsets, preds, scores, id2label))
        assert len(spans) == 2
        assert spans[0].text == "홍길동"
        assert spans[1].text == "김민수"

    def test_unmapped_label_skipped(self):
        from ko_pii.integrations.openai_privacy_filter import OpenAIPrivacyFilterAdapter
        adapter = OpenAIPrivacyFilterAdapter(threshold=0.3)
        text = "2024-01-01"
        offsets = [[0, 4], [4, 5], [5, 7], [7, 8], [8, 10]]
        preds = [0, 1, 1, 1, 1]
        scores = [0.9] * 5
        # DATE_TIME 은 _LABEL_MAP 에서 None 으로 매핑 → 무시
        id2label = {0: "B-DATE_TIME", 1: "I-DATE_TIME"}
        spans = list(adapter._bio_to_spans(text, offsets, preds, scores, id2label))
        assert spans == []
