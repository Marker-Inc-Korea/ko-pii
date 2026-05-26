# MCP Server (Model Context Protocol)

[MCP](https://modelcontextprotocol.io) 는 Anthropic 이 표준화한 LLM 도구
인터페이스. Claude·OpenAI·기타 호환 클라이언트가 ko-pii 를 *함수* 로 호출할
수 있게 함.

## 설치

```bash
pip install ko-pii[mcp]
```

## Claude Desktop 통합

`~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) 또는 `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ko-pii": {
      "command": "ko-pii-mcp-server"
    }
  }
}
```

Claude Desktop 재시작 → "ko-pii" 도구가 Claude 에 자동 표시됨.

## 제공 도구 (LLM 이 호출 가능)

### 1. `detect_pii(text)`
PII 검출만 (가명화 X). 라벨·위치·신뢰도·법적 근거 반환.

```json
{
  "name": "detect_pii",
  "arguments": {"text": "홍길동 880101-1234568"}
}
```

응답:
```json
{
  "count": 2,
  "detections": [
    {
      "label": "PERSON",
      "text": "홍길동",
      "start": 0, "end": 3,
      "risk_level": "HIGH",
      "confidence": 0.65,
      "legal_basis": "개인정보보호법 제2조"
    },
    {
      "label": "RRN", ...
    }
  ]
}
```

### 2. `anonymize(text, mode, strategy, vault_id)`
검출 + 가명화. `vault_id` 가 있으면 같은 세션의 vault 재사용 (같은 사람 →
같은 토큰).

```json
{
  "name": "anonymize",
  "arguments": {
    "text": "신청인 홍길동 880101-1234568",
    "mode": "STRICT",
    "strategy": "tokenize"
  }
}
```

응답:
```json
{
  "text": "신청인 <PERSON_1> <RRN_1>",
  "vault_id": "abc-123-...",
  "combined_risk": "CRITICAL",
  "summary": {...}
}
```

### 3. `reveal(token, vault_id)`
토큰 → 원본 복원 (권한 검사 필요한 환경에서는 별도 wrapping).

```json
{
  "name": "reveal",
  "arguments": {"token": "<RRN_1>", "vault_id": "abc-123-..."}
}
```

### 4. `combined_risk(text)`
결합 위험도 평가 (가이드라인 기준).

## 사용 시나리오

### Claude 사용자가 한국 공문서 처리

```
사용자 → "이 공문서 요약해줘: [긴 한국 공문서]"
       ↓
Claude → (MCP 도구 호출) anonymize(text=..., mode="PARANOID")
       ↓
ko-pii 서버 → 가명화된 텍스트 + vault_id 반환
       ↓
Claude → 가명본으로 요약 생성
       ↓
Claude → (도구 호출) reveal(token=<PERSON_1>, vault_id=...) 필요 시 복원
       ↓
사용자 → 안전한 요약 (PII 가 Claude 학습에 노출 안 됨)
```

### 이점

- **데이터 안전성**: PII 가 LLM 에 *원본 그대로* 노출되지 않음
- **로컬 stdio**: 외부 네트워크 X
- **법적 근거 보존**: detect_pii 응답에 한국 법조항 부착
- **결정성**: 같은 입력 → 같은 토큰 (감사 추적 가능)

## 실행 (수동 테스트)

```bash
# stdio 서버 실행
ko-pii-mcp-server

# JSON-RPC 메시지를 stdin 으로 전달 (테스트용)
```

## 보안 주의

- `reveal` 도구는 *권한 검사 없이* 동작. Production 에서는 wrapping 필수.
- 세션 vault 는 *in-memory* — 프로세스 재시작 시 소실.
  영구 저장은 `ko_pii.vault.ReversibleVault.save()` 또는 `[security]` extras 의
  암호화 vault 사용 권장.
- `KPII_VAULT_PASSWORD` 환경변수로 암호화 vault 자동 로드 가능 (향후 확장).

## MCP 클라이언트 호환성

| 클라이언트 | 호환 |
|---|---|
| Claude Desktop | ✅ (Anthropic 표준) |
| Cline (VS Code) | ✅ |
| OpenAI o1 / GPT-4o (실험) | ⚠️ 부분 |
| Codex (OpenAI) | ⚠️ 부분 |
| 기타 MCP 호환 | ✅ |
