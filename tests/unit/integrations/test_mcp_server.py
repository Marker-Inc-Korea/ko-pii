"""MCP 서버 어댑터 — soft import 안전성 검증.

실제 stdio 서버 실행 테스트는 mcp 설치 + asyncio 환경 필요. 여기서는
module import + main() 진입점 안전성만 확인.
"""
import pytest


class TestSoftImport:
    def test_module_imports_without_mcp(self):
        from ko_pii.integrations import mcp_server as m
        assert hasattr(m, "main")
        assert hasattr(m, "build_server")
        assert hasattr(m, "_register_tools")

    def test_main_without_mcp_returns_error(self, monkeypatch, capsys):
        from ko_pii.integrations import mcp_server as m
        if m._HAS_MCP:
            pytest.skip("mcp 설치됨 — skip")
        result = m.main()
        captured = capsys.readouterr()
        assert result == 1
        assert "mcp" in captured.err.lower() or "MCP" in captured.err
