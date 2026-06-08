# 보안 정책 (Security Policy)

## 지원 버전

| 버전 | 보안 패치 |
|---|---|
| 1.x | ✅ |
| < 1.0 | ❌ |

## 취약점 보고 (Responsible Disclosure)

ko-pii 는 한국 개인정보 검출·가명화 라이브러리로, 잘못된 동작이 직접적인
개인정보 유출로 이어질 수 있습니다. 보안 취약점은 **공개 이슈로 올리지
말아주세요**.

### 보고 채널

- **이메일:** rlaehrud63@gmail.com (제목 prefix: `[ko-pii security]`)
- **GitHub Private Advisory:** https://github.com/Marker-Inc-Korea/ko-pii/security/advisories/new

### 보고에 포함하면 좋은 것

1. 영향 받는 버전 / 환경 (OS, Python, extras)
2. 재현 절차 (최소 코드 + 입력 텍스트, 합성 PII 사용 권장)
3. 예상 피해 시나리오 (검출 누락 / Vault 우회 / 토큰 충돌 등)
4. 가능하면 패치 제안

### 응답 일정 (best-effort)

- 접수 확인: 영업일 기준 3일 이내
- 영향 평가: 7일 이내
- 패치 + 권고문 공개: 심각도에 따라 14~90일 (공개 전 조율)

## 본 라이브러리의 보안 모델

ko-pii 는 **방어 도구** 이며 다음을 가정합니다.

- **신뢰 경계:** 입력 텍스트는 신뢰되지 않을 수 있음 (악의적 입력 가능).
  출력 (가명화 텍스트 + Vault) 은 별도 권한 경계로 분리 저장 가정.
- **Vault 분리 보관:** 가역 가명화의 안전성은 Vault 의 분리 보관에 의존.
  Vault 파일이 유출되면 원본 복원 가능. `[security]` extras 의 AES-256-GCM
  + PBKDF2 480k 반복 권장.
- **체크섬 외 휴리스틱:** PERSON/ADDRESS 등 사전·문맥 기반 검출은
  100% 보장하지 않음 (false negative 가능). 외부 공개 전에는 사람 검수 +
  여러 모드 (`PARANOID` 등) 의 조합 권장.

## 알려진 비-취약점 (Known Non-Issues)

- PERSON/ADDRESS 등 휴리스틱 카테고리의 부분 검출 누락 — *정확도 개선*
  영역이지 보안 취약점은 아님. `docs/EVALUATION_REPORT.md` 참고.
- 합성 코퍼스 회귀 F1 변동 — 일반 버그 트래킹.
