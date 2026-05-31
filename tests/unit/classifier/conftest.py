"""분류기 테스트 — 의존성 없으면 모듈 전체 skip.

[classifier] extras 미설치 시:
- import torch / transformers / sklearn 실패
- 본 디렉토리 전체 collect 단계에서 skip
"""
import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("sklearn")
