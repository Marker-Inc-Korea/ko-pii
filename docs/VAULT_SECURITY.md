# Vault 보안 계약

`ReversibleVault`는 토큰과 원본 개인정보의 대응 관계를 저장하고 복원하는 라이브러리
primitive입니다. 인증 서버나 비밀 관리 시스템이 아닙니다. 이 문서는 기능이 보장하는
범위와 운영자가 별도로 구현해야 하는 경계를 구분합니다.

## 보장하는 기능

- 같은 Vault 안에서 같은 `(label, original)` 값에 같은 토큰을 부여합니다.
- `store()`와 `reveal()` 호출을 선택적으로 JSONL 감사 로그에 기록합니다.
- `[security]` extra를 설치하면 저장 파일을 AES-GCM으로 암호화할 수 있습니다.
- `audit_failure_policy="raise"`를 사용하면 감사 기록 실패 시 처리 또는 복원이 성공으로
  반환되지 않습니다.

## 보장하지 않는 기능

- **인증·인가:** Vault 객체나 복호화 자격증명에 접근한 호출자를 검사하지 않습니다.
- **키 관리:** 암호의 발급·회전·폐기, KMS/HSM 연동과 비밀 전달은 애플리케이션 책임입니다.
- **감사 로그 무결성:** 기본 JSONL은 append 형식일 뿐 서명되거나 변조 방지된 원장은
  아닙니다. 별도 수집기, WORM 저장소 또는 서명 계층이 필요할 수 있습니다.
- **actor 신원 확인:** actor/context 필드는 호출자가 제공하거나 로컬 계정에서 추정한
  메타데이터이며 인증된 사용자 신원을 증명하지 않습니다.
- **호스트 침해 방어:** 파일 암호화는 저장 상태를 보호하지만, 복호화된 Vault가 메모리에
  열린 동안 같은 프로세스나 침해된 호스트로부터 보호하지 않습니다.
- **법적 익명성:** 복원 가능한 토큰화는 익명화가 아니라 가명화입니다.

## 저장 형식과 실패 정책

`ReversibleVault.save()`와 암호 없는 CLI `--vault`는 원본 개인정보가 포함된 평문 JSON을
씁니다. 운영 환경에서는 `ko-pii[security]`와 `KPII_VAULT_PASSWORD` 또는 별도 보안 저장소를
사용하십시오. CLI는 평문 저장 시 경고합니다.

라이브러리는 기존 코드와의 호환성을 위해 감사 실패 정책의 기본값이 `best_effort`입니다.
감사 로그를 통제 증거로 사용하는 경로에서는 명시적으로 실패 폐쇄를 선택하십시오.

```python
from ko_pii import ReversibleVault
from ko_pii.vault import AuditLog

with AuditLog("audit.jsonl") as audit:
    vault = ReversibleVault(
        audit_log=audit,
        audit_failure_policy="raise",
    )
```

CLI에서 `--audit-log`를 지정하면 기본 실패 정책은 `raise`입니다. 가용성을 우선해 기존
동작이 필요한 경우에만 `--audit-failure-policy best_effort`를 명시하십시오.
CLI의 `anonymize` 이벤트는 `status="prepared"`로 기록됩니다. 이는 가명화 결과가 메모리에
준비됐다는 뜻이며, 이후 출력 파일·Vault·리포트 저장까지 성공했다는 트랜잭션 증거는 아닙니다.
JSONL 감사 파일과 여러 출력 대상을 하나의 원자적 트랜잭션으로 묶지는 않습니다.
CLI 배치 모드는 파일별 독립 처리이므로 `--vault`, `--vault-password`, `--audit-log`를
지원하지 않으며, 해당 조합은 오류로 종료됩니다. 가역성과 감사 증거가 필요한 문서는 단일
파일 모드 또는 Vault 수명 주기를 직접 관리하는 Python API로 처리하십시오.

## 연결 가능성과 격리

같은 Vault를 여러 문서에서 재사용하면 동일한 값이 동일 토큰으로 치환되어 문서 간 연결이
가능합니다. 이는 RAG 문맥 유지에는 유용하지만 재식별 단서가 될 수 있습니다. 필요한
일관성 범위를 먼저 정한 뒤 tenant, 목적, 보존기간 또는 작업 단위로 Vault를 분리하십시오.
서로 다른 Vault를 쓰더라도 같은 salt와 비밀 키를 재사용하는 hashed/FPE 구성은 별도 연결
가능성을 만들 수 있습니다.

## 운영 체크리스트

1. 복원이 필요하지 않으면 `redact`, `partial` 또는 `asterisk`를 사용합니다.
2. Vault와 가명화 결과를 서로 다른 접근 정책과 저장 위치에 둡니다.
3. 파일 권한, IAM/ACL, 키 회전, 백업·복제본과 삭제 기한을 정의합니다.
4. 복원 API 앞에서 사용자·서비스 권한과 업무 사유를 검사하고 actor/context를 전달합니다.
5. 감사 증거가 필수인 경로는 `audit_failure_policy="raise"`로 실행합니다.
6. 감사 로그를 중앙 수집하고 보존·무결성·접근 정책을 별도로 적용합니다.
7. tenant와 목적을 넘는 동일 토큰 연결이 필요한지 검토하고 Vault 범위를 최소화합니다.
