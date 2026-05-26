from ko_pii.context.context_rules import NameCandidate, score_candidate


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
