"""__version__ ↔ pyproject.toml 동기화 가드 — 1.13.1~1.15.0 에서 표류했던 회귀 방지."""
import re
from pathlib import Path

import ko_pii


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    m = re.search(r'^version = "([^"]+)"', pyproject.read_text(encoding="utf-8"),
                  re.MULTILINE)
    assert m, "pyproject.toml 에서 version 을 찾지 못함"
    assert ko_pii.__version__ == m.group(1)
