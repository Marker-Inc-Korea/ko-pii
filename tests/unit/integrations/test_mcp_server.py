"""Optional MCP SDK compatibility, tested over the actual stdio transport."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import sys

import pytest


class TestSoftImport:
    def test_module_imports_without_mcp(self):
        from ko_pii.integrations import mcp_server as module
        assert callable(module.main)
        assert callable(module.build_server)

    def test_main_without_mcp_returns_error(self, monkeypatch, capsys):
        from ko_pii.integrations import mcp_server as module
        monkeypatch.setattr(module, "_HAS_MCP", False)
        assert module.main() == 1
        captured = capsys.readouterr()
        assert "pip install ko-pii[mcp]" in captured.err
        assert captured.out == ""


def test_unsupported_sdk_reports_install_hint(monkeypatch):
    from ko_pii.integrations import mcp_server as module
    monkeypatch.setattr(module, "_HAS_MCP", True)
    monkeypatch.setattr(module, "Server", object, raising=False)
    with pytest.raises(ImportError, match="mcp>=1.28.1,<3"):
        module.build_server()


def test_sdk_warning_retains_diagnostic_without_raw_tool_name():
    from ko_pii.integrations.mcp_server import _ToolNameLogFilter
    record = logging.LogRecord("mcp", logging.WARNING, "", 0,
                               "Tool '%s' not listed, no validation will be performed",
                               ("secret@example.com",), None)
    assert _ToolNameLogFilter().filter(record)
    assert record.getMessage() == "Unknown MCP tool requested"
    record.msg, record.args = "Other warning %s", ("retained",)
    assert _ToolNameLogFilter().filter(record)
    assert record.getMessage() == "Other warning retained"


@asynccontextmanager
async def connected_session(stderr):
    import mcp
    from mcp.client.stdio import stdio_client
    import ko_pii

    # Use exactly the package under test, including in editable/source runs.
    env = dict(os.environ, PYTHONPATH=str(Path(ko_pii.__file__).resolve().parent.parent))
    parameters = mcp.StdioServerParameters(
        command=sys.executable, args=["-m", "ko_pii.integrations.mcp_server"], env=env,
    )
    async with stdio_client(parameters, errlog=stderr) as (reader, writer):
        async with mcp.ClientSession(reader, writer) as session:
            info = await session.initialize()
            assert info.model_dump(by_alias=True)["serverInfo"]["name"] == "ko-pii"
            yield session


def run_stdio(tmp_path, exercise):
    pytest.importorskip("mcp")
    log = tmp_path / "server.log"
    with log.open("w", encoding="utf-8") as stderr:
        async def bounded():
            async with connected_session(stderr) as session:
                await exercise(session)
        asyncio.run(asyncio.wait_for(bounded(), timeout=30))
    return log.read_text(encoding="utf-8")


def payload(result):
    assert not result.model_dump(by_alias=True)["isError"]
    return json.loads(result.content[0].text)


def test_real_stdio_all_tools_and_vault_reuse(tmp_path):
    async def exercise(session):
        tools = {t.name: t.model_dump(by_alias=True) for t in (await session.list_tools()).tools}
        assert set(tools) == {"anonymize", "detect_pii", "reveal", "combined_risk"}
        assert tools["anonymize"]["inputSchema"]["required"] == ["text"]
        assert tools["anonymize"]["inputSchema"]["properties"]["mode"]["default"] == "STRICT"
        masked = payload(await session.call_tool("anonymize", {"text": "메일 demo@example.com"}))
        assert masked["text"] == "메일 <EMAIL_1>"
        reused = payload(await session.call_tool("anonymize", {
            "text": "demo@example.com next@example.com", "vault_id": masked["vault_id"],
        }))
        assert reused["text"] == "<EMAIL_1> <EMAIL_2>"
        revealed = payload(await session.call_tool("reveal", {
            "vault_id": masked["vault_id"], "token": "<EMAIL_1>",
        }))
        assert revealed == {"token": "<EMAIL_1>", "original": "demo@example.com", "found": True}
        missing = payload(await session.call_tool("reveal", {
            "vault_id": masked["vault_id"], "token": "<EMAIL_999>",
        }))
        assert missing["original"] is None and missing["found"] is False
        detected = payload(await session.call_tool("detect_pii", {"text": "demo@example.com"}))
        assert detected["count"] == 1
        assert detected["detections"][0]["text"] == "demo@example.com"
        risk = payload(await session.call_tool("combined_risk", {"text": "demo@example.com"}))
        assert set(risk) == {"risk_level", "rationale", "identifiers", "quasi_identifiers", "sensitive_attributes"}
        empty = payload(await session.call_tool("anonymize", {"text": ""}))
        assert empty["text"] == ""
    log = run_stdio(tmp_path, exercise)
    assert "demo@example.com" not in log


@pytest.mark.parametrize("name,arguments", [
    ("anonymize", {}),
    ("anonymize", {"text": 42}),
    ("anonymize", {"text": ["secret@example.com"]}),
    ("anonymize", {"text": None}),
    ("anonymize", {"text": "secret@example.com", "mode": "secret@example.com"}),
    ("anonymize", {"text": "secret@example.com", "strategy": "secret@example.com"}),
    ("anonymize", {"text": "secret@example.com", "vault_id": 42}),
    ("detect_pii", {"text": {"secret@example.com": 1}}),
    ("combined_risk", {}),
    ("reveal", {"token": "secret@example.com"}),
    ("reveal", {"token": "<EMAIL_1>", "vault_id": "secret@example.com"}),
    ("secret@example.com", {"text": "secret@example.com"}),
])
def test_stdio_rejects_bad_calls_without_echoing_pii(tmp_path, name, arguments):
    async def exercise(session):
        result = await session.call_tool(name, arguments)
        assert result.model_dump(by_alias=True)["isError"]
        assert "secret@example.com" not in result.model_dump_json()
        assert json.loads(result.content[0].text)["error"]
        # A bad call must not terminate the process or poison the next call.
        assert payload(await session.call_tool("anonymize", {"text": "ok@example.com"}))["text"] == "<EMAIL_1>"
    assert "secret@example.com" not in run_stdio(tmp_path, exercise)
