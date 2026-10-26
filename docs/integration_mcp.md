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

### 호스트에서 도구를 호출하는 흐름과 주의점

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
사용자 → 요약 (원문 입력과 복원 응답의 전송 범위는 호스트가 결정)
```

### 이점

- **로컬 처리**: ko-pii 서버 자체는 모델이나 외부 API를 호출하지 않음
- **전송 경계는 별도**: 이미 모델에 입력한 원문을 사후에 가명화해도 이전 전송은 취소되지 않음
- **법적 근거 보존**: detect_pii 응답에 한국 법조항 부착
- **토큰 일관성**: 같은 Vault에서 같은 라벨/값은 같은 토큰 사용

이 MCP 서버는 외부 전송 전 필터가 아닙니다. detect_pii의 text/evidence와 reveal의
original은 원문을 포함할 수 있으며 호스트가 도구 결과를 모델에 보낼 수 있습니다.
모델 호출 전에 별도 로컬 Python/CLI 전처리를 수행하고 가명본만 전달해야 원문의
전송을 줄일 수 있습니다. 미탐은 가능하며 공급자의 학습·보관 정책을 이 도구가
통제하거나 보증하지 않습니다. 비밀 원문으로 호스트 연결을 시험하지 마세요.

## 실행 (수동 테스트)

```bash
# stdio 서버 실행
ko-pii-mcp-server

# JSON-RPC 메시지를 stdin 으로 전달 (테스트용)
```

## 보안 주의

- `reveal` 도구는 *권한 검사 없이* 동작. Production 에서는 wrapping 필수.
- 세션 vault 는 *in-memory* — 프로세스 재시작 시 소실.
  `ReversibleVault.save()`는 원본 PII가 담긴 평문 JSON이므로 운영 영구 저장에는
  `[security]` extra의 암호화 vault 또는 별도 보안 저장소를 사용.
- actor/context는 감사 메타데이터일 뿐 인증된 사용자 신원을 증명하지 않음.
- `KPII_VAULT_PASSWORD`에 의한 MCP Vault 자동 로드/저장은 구현되어 있지 않습니다.

## 검증 범위

CI는 설치된 MCP SDK의 도구 목록과 호출 응답을 합성 입력으로 검사합니다.
이 어댑터는 SDK 1.x의 서버 API를 사용하므로 extra는 `mcp>=1.0,<2`로 제한합니다.
SDK 2.x는 서버 API가 달라 현재 지원하지 않습니다.
각 호스트의 로그인·권한 승인·모델 전송 설정이나 stdio 전체 왕복의 호환성 보증은
아닙니다. 호스트 버전별 설정을 확인하고 원문 복원 도구는 승인 없이 자동 실행하지 마세요.
