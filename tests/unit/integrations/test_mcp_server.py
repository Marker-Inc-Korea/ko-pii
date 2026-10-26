"""Soft imports, SDK handlers, and an optional real MCP stdio round trip."""
import pytest
import asyncio
import json
import sys


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


def test_unsupported_sdk_reports_install_hint(monkeypatch):
    from ko_pii.integrations import mcp_server as module
    monkeypatch.setattr(module, "_HAS_MCP", True)
    monkeypatch.setattr(module, "Server", object, raising=False)
    with pytest.raises(ImportError, match="mcp>=1.0,<2"):
        module.build_server()


def test_real_sdk_tool_list_calls_and_invalid_input(monkeypatch):
    types = pytest.importorskip("mcp.types")
    from ko_pii.integrations import mcp_server as module
    monkeypatch.setattr(module, "_VAULTS", {})
    server = module.build_server()

    async def exercise():
        listing = await server.request_handlers[types.ListToolsRequest](
            types.ListToolsRequest(method="tools/list"))
        assert {tool.name for tool in listing.root.tools} == {
            "detect_pii", "anonymize", "reveal", "combined_risk",
        }

        async def call(name, arguments):
            result = await server.request_handlers[types.CallToolRequest](
                types.CallToolRequest(method="tools/call", params=types.CallToolRequestParams(
                    name=name, arguments=arguments)))
            return result.root

        masked = await call("anonymize", {"text": "demo@example.com"})
        assert not masked.isError
        value = json.loads(masked.content[0].text)
        assert value["text"] == "<EMAIL_1>"
        revealed = await call("reveal", {"token": "<EMAIL_1>", "vault_id": value["vault_id"]})
        assert json.loads(revealed.content[0].text)["original"] == "demo@example.com"
        detected = await call("detect_pii", {"text": "demo@example.com"})
        assert json.loads(detected.content[0].text)["detections"][0]["text"] == "demo@example.com"
        invalid = await call("anonymize", {"text": 42})
        assert invalid.isError

    asyncio.run(exercise())


def test_real_stdio_initialize_mask_and_reveal():
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client

    async def exercise():
        parameters = mcp.StdioServerParameters(command=sys.executable,
                                               args=["-m", "ko_pii.integrations.mcp_server"])
        async with stdio_client(parameters) as (reader, writer):
            async with mcp.ClientSession(reader, writer) as session:
                info = await session.initialize()
                assert info.serverInfo.name == "ko-pii"
                assert {t.name for t in (await session.list_tools()).tools} == {
                    "anonymize", "detect_pii", "reveal", "combined_risk",
                }
                response = await session.call_tool("anonymize", {"text": "demo@example.com"})
                assert not response.isError
                masked = json.loads(response.content[0].text)
                assert masked["text"] == "<EMAIL_1>"
                revealed = await session.call_tool("reveal", {
                    "vault_id": masked["vault_id"], "token": "<EMAIL_1>"})
                assert json.loads(revealed.content[0].text)["original"] == "demo@example.com"
                assert (await session.call_tool("anonymize", {"text": 42})).isError

    async def bounded():
        await asyncio.wait_for(exercise(), timeout=30)

    asyncio.run(bounded())
