import pytest

from ko_pii.context.context_rules import (
    NameCandidate, _agency_sentence_boundaries, _has_agency_in_sentence, score_candidate,
)


def _score(text, name, **kwargs):
    start = text.index(name)
    end = start + len(name)
    cand = NameCandidate(name=name, start=start, end=end)
    return score_candidate(text, cand, **kwargs)


class TestPositiveSignals:
    def test_field_label_strong_boost(self):
        s = _score("성명: 홍길동", "홍길동")
        assert s.value >= 0.55
        assert any("field_label" in e for e in s.evidence)

    def test_title_adjacent_boost(self):
        s = _score("기획재정부 김철수 과장", "김철수")
        assert s.value >= 0.55
        assert any("title" in e for e in s.evidence)

    def test_particle_attached(self):
        s = _score("홍길동이 신청했다", "홍길동")
        assert any("particle" in e for e in s.evidence)

    def test_deterministic_pii_nearby(self):
        s = _score("홍길동 880101-1234568", "홍길동", deterministic_nearby=True)
        assert any("deterministic_pii" in e for e in s.evidence)
        assert s.value >= 0.45  # 0.15 (surname) + 0.40 (3자 det) + bonuses


class TestNegativeSignals:
    def test_common_word_dropped(self):
        # "김치" is in common words → strong negative
        s = _score("김치는 한국 음식이다", "김치")
        assert any("common_word" in e for e in s.evidence)

    def test_single_char_penalised(self):
        s = _score("그는 박이다", "박")
        assert s.value < 0.5  # length-1 + no other strong signals


@pytest.mark.parametrize("text", [
    "", ".", "\n", "환경부", "환경부.", "환경부\n", "환경부\n\n김철수.",
    "환경부 김철수. 인사처 이영희\n아무 기관도 없는 문장", "환경부? 김철수! 이영희.",
])
def test_indexed_agency_context_matches_the_standalone_boundary_rules(text):
    boundaries = _agency_sentence_boundaries(text)
    cache = {}
    for start in range(len(text) + 1):
        for end in range(start, len(text) + 1):
            expected = _has_agency_in_sentence(text, start, end)
            assert _has_agency_in_sentence(text, start, end, cache, boundaries=boundaries) == expected


def test_person_pipeline_does_not_rescan_the_document_for_each_sentence_boundary():
    from ko_pii.patterns.person import detect

    class CountingText(str):
        boundary_searches = 0

        def find(self, *args):
            self.boundary_searches += 1
            return super().find(*args)

        def rfind(self, *args):
            self.boundary_searches += 1
            return super().rfind(*args)

    text = CountingText("환경부 김철수 김영희 " * 200)
    list(detect(text))
    assert text.boundary_searches == 0
