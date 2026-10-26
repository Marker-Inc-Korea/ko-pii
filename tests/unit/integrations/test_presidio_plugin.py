"""Presidio plugin — soft import + 라벨 매핑 검증.

실제 Presidio 동작 테스트는 ``pip install ko-pii[presidio]`` 후만 가능.
여기서는 import 안전성 + 라벨 매핑·메타데이터 검증.
"""
import pytest
from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]


def test_documented_example_matches_executable_file():
    example = (ROOT / "examples/presidio_rules.py").read_text(encoding="utf-8").strip()
    assert f"```python\n{example}\n```" in (ROOT / "docs/integration_presidio.md").read_text(encoding="utf-8")


def test_actual_presidio_example_without_model_download(tmp_path):
    pytest.importorskip("presidio_analyzer")
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples/presidio_rules.py")], cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH="", PYTHONUTF8="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    assert "<EMAIL_ADDRESS>" in result.stdout and "<PHONE_NUMBER>" in result.stdout
    assert "demo@example.com" not in result.stdout
    assert "010-2345-6789" not in result.stdout


class TestSoftImport:
    def test_module_imports_without_presidio(self):
        # presidio 없어도 import 자체는 가능
        from ko_pii.integrations import presidio_plugin as p
        assert hasattr(p, "KPiiRecognizer")
        assert hasattr(p, "_PRESIDIO_LABEL_MAP")

    def test_init_without_presidio_raises(self, monkeypatch):
        from ko_pii.integrations import presidio_plugin as p
        if p._HAS_PRESIDIO:
            pytest.skip("presidio 설치되어 있음 — skip")
        with pytest.raises(ImportError, match="presidio"):
            p.KPiiRecognizer()


class TestLabelMap:
    def test_korean_specific_labels(self):
        from ko_pii.integrations.presidio_plugin import _PRESIDIO_LABEL_MAP
        # 한국 특화 라벨은 KR_ prefix
        assert _PRESIDIO_LABEL_MAP["RRN"] == "KR_RRN"
        assert _PRESIDIO_LABEL_MAP["FRN"] == "KR_FRN"
        assert _PRESIDIO_LABEL_MAP["BUSINESS_REG"] == "KR_BUSINESS_REG"
        assert _PRESIDIO_LABEL_MAP["VEHICLE"] == "KR_VEHICLE_PLATE"
        assert _PRESIDIO_LABEL_MAP["EDI_DRUG"] == "KR_EDI_DRUG"

    def test_presidio_standard_labels(self):
        from ko_pii.integrations.presidio_plugin import _PRESIDIO_LABEL_MAP
        # 표준 Presidio 라벨 매핑
        assert _PRESIDIO_LABEL_MAP["CARD"] == "CREDIT_CARD"
        assert _PRESIDIO_LABEL_MAP["PHONE"] == "PHONE_NUMBER"
        assert _PRESIDIO_LABEL_MAP["EMAIL"] == "EMAIL_ADDRESS"
        assert _PRESIDIO_LABEL_MAP["IP"] == "IP_ADDRESS"
        assert _PRESIDIO_LABEL_MAP["URL"] == "URL"
        assert _PRESIDIO_LABEL_MAP["PERSON"] == "PERSON"

    def test_supported_entities_unique(self):
        from ko_pii.integrations.presidio_plugin import _get_supported_entities
        entities = _get_supported_entities()
        # 중복 없음
        assert len(entities) == len(set(entities))
        # 최소 한국 특화 라벨 포함
        assert "KR_RRN" in entities
        assert "PHONE_NUMBER" in entities
