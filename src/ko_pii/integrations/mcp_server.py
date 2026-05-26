"""MCP (Model Context Protocol) 서버 — LLM 이 ko-pii 를 *도구* 로 호출.

MCP 는 Anthropic 이 표준화한 LLM 도구 인터페이스 프로토콜.
Claude·OpenAI·기타 호환 클라이언트가 stdio/HTTP 로 본 서버에 연결하여
ko-pii 의 기능을 *함수* 처럼 호출할 수 있다.

설치::

    pip install ko-pii[mcp]

실행 (stdio 모드, LLM 클라이언트 통합용)::

    ko-pii-mcp-server

또는 Claude Desktop / Cline 등의 ``mcp_settings.json`` 에 등록::

    {
      "mcpServers": {
        "ko-pii": {
          "command": "ko-pii-mcp-server"
        }
      }
    }

제공 도구 (LLM 이 호출 가능):
- ``detect_pii(text)`` — PII 검출만 (가명화 X)
- ``anonymize(text, mode, strategy)`` — 가명화 + 결과 본문 반환
- ``reveal(token, vault_id)`` — 토큰에서 원본 복원 (권한 검사 후)
- ``combined_risk(text)`` — 결합 위험도 평가

본 서버는 *로컬 stdio* 만 사용 — 외부 네트워크 X. PII 데이터 외부 유출 없음.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Optional

try:
    from mcp.server import Server  # type: ignore
    from mcp.server.stdio import stdio_server  # type: ignore
    import mcp.types as types  # type: ignore
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def _ensure_mcp() -> None:
    if not _HAS_MCP:
        raise ImportError(
            "MCP 서버는 'mcp' 패키지가 필요합니다.\n"
            "  pip install ko-pii[mcp]\n"
            "또는 pip install mcp"
        )


# 세션별 vault 관리 (in-memory)
_VAULTS: dict[str, "object"] = {}


def _register_tools(server):
    @server.list_tools()
    async def list_tools():
        return [
            types.Tool(
                name="detect_pii",
                description=(
                    "한국 공공 PII 검출. text 를 분석해 검출된 PII 의 라벨·위치·"
                    "신뢰도·법적 근거를 JSON 으로 반환. 가명화는 하지 않음."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "분석할 텍스트"},
                    },
                    "required": ["text"],
                },
            ),
            types.Tool(
                name="anonymize",
                description=(
                    "한국 공공 PII 검출 + 가명화. vault_id 가 있으면 같은 세션의 "
                    "기존 vault 재사용 (같은 사람 → 같은 토큰)."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["PARANOID", "STRICT", "BALANCED",
                                     "PERMISSIVE", "AUDIT"],
                            "default": "STRICT",
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["tokenize", "redact", "asterisk",
                                     "hashed", "partial", "fpe"],
                            "default": "tokenize",
                        },
                        "vault_id": {
                            "type": "string",
                            "description": "세션 vault ID (옵션)",
                        },
                    },
                    "required": ["text"],
                },
            ),
            types.Tool(
                name="reveal",
                description=(
                    "토큰에서 원본 PII 복원. vault_id 와 token 필요. "
                    "경고: 감사 로그가 활성화되지 않은 환경에서 호출 시 추적 불가."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "token": {"type": "string", "description": "예: <RRN_1>"},
                        "vault_id": {"type": "string"},
                    },
                    "required": ["token", "vault_id"],
                },
            ),
            types.Tool(
                name="combined_risk",
                description=(
                    "텍스트의 결합 위험도 평가 — 「개인정보 비식별 조치 가이드라인」 "
                    "기준 식별자/준식별자/민감속성 분류 후 종합 위험도 산출."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                    },
                    "required": ["text"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from ko_pii import Anonymizer, ProcessingMode
        from ko_pii.detect import detect_all
        from ko_pii.analytics import score_combined_risk

        if name == "detect_pii":
            text = arguments["text"]
            detections = detect_all(text)
            payload = {
                "count": len(detections),
                "detections": [
                    {
                        "label": d.label,
                        "text": d.text,
                        "start": d.start,
                        "end": d.end,
                        "risk_level": d.risk_level.name,
                        "confidence": d.confidence,
                        "legal_basis": d.legal_basis,
                        "evidence": list(d.evidence),
                    }
                    for d in detections
                ],
            }
            return [types.TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )]

        if name == "anonymize":
            from ko_pii.vault.reversible import ReversibleVault

            text = arguments["text"]
            mode = ProcessingMode(arguments.get("mode", "STRICT"))
            strategy = arguments.get("strategy", "tokenize")
            vault_id = arguments.get("vault_id")

            if vault_id and vault_id in _VAULTS:
                vault = _VAULTS[vault_id]
            else:
                vault = ReversibleVault()
                if not vault_id:
                    vault_id = str(uuid.uuid4())
                _VAULTS[vault_id] = vault

            anon = Anonymizer(mode=mode, strategy=strategy, vault=vault)
            result = anon.process(text)

            payload = {
                "text": result.text,
                "vault_id": vault_id,
                "combined_risk": result.combined_risk.combined_risk.name,
                "summary": result.summary,
            }
            return [types.TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )]

        if name == "reveal":
            token = arguments["token"]
            vault_id = arguments["vault_id"]
            vault = _VAULTS.get(vault_id)
            if vault is None:
                return [types.TextContent(
                    type="text",
                    text=json.dumps({"error": f"unknown vault_id: {vault_id}"},
                                    ensure_ascii=False),
                )]
            original = vault.reveal(token, context="MCP reveal")
            payload = {
                "token": token,
                "original": original,
                "found": original is not None,
            }
            return [types.TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )]

        if name == "combined_risk":
            text = arguments["text"]
            detections = detect_all(text)
            cr = score_combined_risk(detections)
            payload = {
                "risk_level": cr.combined_risk.name,
                "rationale": list(cr.rationale),
                "identifiers": list(cr.distinct_identifiers),
                "quasi_identifiers": list(cr.distinct_quasi),
                "sensitive_attributes": list(cr.sensitive_present),
            }
            return [types.TextContent(
                type="text",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
            )]

        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False),
        )]


def build_server():
    _ensure_mcp()
    server = Server("ko-pii")
    _register_tools(server)
    return server


async def _run():
    server = build_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> int:
    """ko-pii-mcp-server CLI entry point."""
    try:
        _ensure_mcp()
    except ImportError as e:
        print(f"{e}", file=sys.stderr)
        return 1
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
