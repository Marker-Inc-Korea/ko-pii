# ko-pii

[English](README.en.md) · [PyPI](https://pypi.org/project/ko-pii/) · [변경 이력](CHANGELOG.md)

한국어 텍스트의 개인정보를 탐지하고 가명화하는 Python 라이브러리입니다.
코어는 모델 다운로드나 외부 API 없이 규칙·사전·형식 검증으로 동작합니다.
Python 3.10 이상, 코드 MIT 라이선스, 코어 런타임 의존성 없음.

## 먼저 사용하기

```bash
python -m pip install ko-pii
```

아래 예제는 [실행 파일](examples/quickstart.py)과 동일하며 CI에서 설치한 wheel로 검사합니다.

```python
from ko_pii import Anonymizer, ProcessingMode

result = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    include={"EMAIL", "PHONE"},
).process("Email: demo@example.com / Tel: 010-2345-6789")

print(result.text)
assert "demo@example.com" not in result.text
assert "010-2345-6789" not in result.text
assert result.vault.reveal("<EMAIL_1>") == "demo@example.com"
```

`tokenize`는 원문을 없애지 않고 Vault로 옮깁니다. Vault에 접근할 수 있는 코드는
원문을 복원할 수 있으므로 출력과 분리 보관하세요. 인증·인가는 호출 애플리케이션의 책임입니다.

## 무엇을 처리하나

- 주민등록번호·전화번호·이메일·카드 등 구조적 식별자와 한국어 이름·주소 등 33개 라벨.
- 토큰 치환, 일부 마스킹, 삭제형 치환 등 처리 전략과 라벨별 정책.
- JSON/JSONL의 필드·배열 경로별 설정과 명시적 필드 라벨.
- 재사용 가능한 `PolicyProfile`, 정책 변경 전후 비교, 값 없는 설명 보고서.
- 알려진 값의 `LiteralDetector`와 신뢰된 코드용 정규식·콜백 확장 지점.
- 선택적 문서 형식 처리와 Vault 암호화. ML/RAG 연동은 별도 extras이며 코어에 필요하지 않습니다.

최신 릴리스의 정확한 변경 범위는 [CHANGELOG](CHANGELOG.md)를 확인하세요.

## CLI와 같은 정책 재사용

저장소의 [정책 예제](examples/policy.json)는 EMAIL과 PHONE을 STRICT/redact로 처리합니다.
아래 명령은 저장소 루트에서 실행하며, 입력 예제와 정책을 함께 제공합니다.

```bash
ko-pii examples/input.txt --policy examples/policy.json --output masked.txt
ko-pii examples/request.json --format json --policy examples/policy.json --output masked.json
```

명령 사용법은 `ko-pii --help`, 상세한 설정은 [정책 안내](docs/POLICY_PROFILES.md)를
참고하세요. JSON 처리와 필드 규칙은 [구조화 처리](docs/STRUCTURED_PROCESSING.md)에 있습니다.

## 도입 전에 확인할 것

이 라이브러리는 모든 개인정보의 제거, 법적 익명성 또는 규정 준수를 보장하지 않습니다.
형식·체크섬 검증이 있어도 미탐과 오탐이 가능합니다. 이름·비정형 주소는 특히 도메인에
의존합니다. 위험도는 보조 휴리스틱이지 법적 판정이 아닙니다.

자기 문서에서 필요한 라벨을 정하고 **탐지 성능과 실제 출력에 남는 값**을 따로 검증하세요.
샘플 몇십 건의 성공은 낮은 유출률의 통계적 증명이 아닙니다. 공개·외부 전송 전에는
업무별 검토와 승인 정책이 필요합니다. 테스트·버그 보고에는 실제 개인정보를 넣지 마세요.

[외부 평가 프로토콜과 결과](research/README.md)는 데이터 리비전·라벨 범위·표본 선정법을
함께 공개합니다. 과거 F1/속도 수치는 당시 조건의 기록이며 현재 버전이나 고객 환경의
성능 보증으로 쓰지 않습니다.

## 문서

| 필요 | 안내 |
|---|---|
| 기능별 문서 찾기 | [문서 목차](docs/README.md) |
| 파일 형식·추출 한계 | [파일 처리](docs/FILE_PROCESSING.md) |
| Vault·키·권한 경계 | [Vault 보안](docs/VAULT_SECURITY.md) |
| 사용자 규칙·추적 | [확장과 설명](docs/SCOPED_RULES_AND_TRACE.md) |
| 도메인 검증·회귀 비교 | [평가](docs/DOMAIN_EVALUATION.md) |
| API·CLI·저장 형식 호환성 | [호환성 정책](docs/COMPATIBILITY.md) |
| 개발·배포 검사 | [기여 안내](CONTRIBUTING.md) |
| 취약점 비공개 보고 | [보안 정책](SECURITY.md) |

## 개발 상태와 자료 구분

Ubuntu Python 3.10/3.12/3.14, Windows/macOS CLI, 선택적 RAG 연동을 CI에서 검사합니다.
배포 태그도 같은 검증을 다시 실행하며, 설치 테스트를 통과한 배포 파일만 PyPI로 보냅니다.
이 검사는 패키지 동작에 대한 것으로 실제 개인정보 제거율을 보증하지 않습니다.

`src/`는 제품 코드, `tests/`와 `examples/`는 유지되는 검증 대상입니다.
`data/`의 과거 연구 스크립트·결과는 별도 [목록](research/catalog.json)으로 관리하며
PyPI 패키지에 포함하지 않습니다. 데이터 라이선스는 코드 MIT와 별개입니다.
이전 긴 소개는 [1.22.0 README](https://github.com/Marker-Inc-Korea/ko-pii/blob/v1.22.0/README.md)에 보존되어 있습니다.
