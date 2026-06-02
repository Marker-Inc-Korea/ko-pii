"""KDPII 채점 정합 회귀 테스트.

세 모듈에 매칭 알고리즘이 따로 존재해 숫자가 갈리던 결함을 막는다:
단일 canonical 매처(``kdpii.match_forms_overlap``) + 진입점별 person_min_length
기본값 통일(=3).
"""
import inspect

from ko_pii.eval import kdpii, model_comparison


class TestCanonicalMatcher:
    def test_match_forms_overlap_is_public(self):
        assert hasattr(kdpii, "match_forms_overlap")

    def test_exact_match(self):
        mp, mg = kdpii.match_forms_overlap({"홍길동"}, {"홍길동"})
        assert mp == {"홍길동"} and mg == {"홍길동"}

    def test_substring_match_when_both_2char_plus(self):
        # 부분문자열 매칭 허용 — 단 짧은 쪽이 2자 이상일 때만
        mp, mg = kdpii.match_forms_overlap({"역삼동 123"}, {"역삼동"})
        assert mp == {"역삼동 123"} and mg == {"역삼동"}

    def test_one_char_substring_rejected(self):
        # 1자 예측이 풀네임 gold 의 부분문자열로 TP 처리되던 recall 부풀림 차단
        mp, mg = kdpii.match_forms_overlap({"김"}, {"김철수"})
        assert mp == set() and mg == set()


class TestSingleMatcherAcrossModules:
    def test_three_way_uses_canonical_matcher(self):
        # run_kdpii_three_way 가 중복 인라인 매처가 아니라 canonical 함수를 써야 함
        src = inspect.getsource(model_comparison.run_kdpii_three_way)
        assert "match_forms_overlap" in src
        assert "pi in gi or gi in pi" not in src  # 옛 인라인 매처 잔존 금지


class TestPersonMinLengthUnified:
    def test_defaults_all_three(self):
        # evaluate_kdpii · run_kdpii_three_way 기본값이 동일(3)해야 함
        ek = inspect.signature(kdpii.evaluate_kdpii).parameters["person_min_length"].default
        tw = inspect.signature(model_comparison.run_kdpii_three_way).parameters[
            "person_min_length"
        ].default
        assert ek == tw == 3
