"""labels 레지스트리 — 33종 정본·동기화 가드 + CLI --labels."""
import pytest

from ko_pii.labels import ALL_LABELS, GROUPS, LABEL_INFO, format_labels_table


class TestRegistry:
    def test_exactly_33_labels(self):
        assert len(ALL_LABELS) == 33

    def test_synced_with_redact_korean_names(self):
        # 한글명 정본은 redact 치환명과 동일해야 함 — 드리프트 가드
        from ko_pii.modes.redact import _LABEL_TO_HANGUL
        assert set(ALL_LABELS) == set(_LABEL_TO_HANGUL)
        for k in ALL_LABELS:
            assert LABEL_INFO[k][0] == _LABEL_TO_HANGUL[k], k

    def test_every_label_has_known_group(self):
        for k, (_, group, _) in LABEL_INFO.items():
            assert group in GROUPS, k

    def test_table_contains_all_labels(self):
        t = format_labels_table()
        for k in ALL_LABELS:
            assert k in t


class TestCliLabels:
    def test_labels_flag_prints_and_exits_zero(self, capsys):
        from ko_pii.cli import main
        assert main(["--labels"]) == 0
        out = capsys.readouterr().out
        assert "33종" in out and "PERSON" in out and "RRN" in out

    def test_missing_input_still_errors(self):
        from ko_pii.cli import main
        with pytest.raises(SystemExit) as e:
            main([])
        assert e.value.code == 2
