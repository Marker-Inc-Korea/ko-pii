# 직접 변환 API의 입력 경계

일반 사용에는 탐지와 정책을 함께 적용하는 `Anonymizer.process()`를 권장합니다.
직접 `tokenize`, `redact`, `hashed`, `partial`, `fpe`를 호출하는 경우에는 호출자가
같은 원문에서 만든 `DetectionResult`를 전달해야 합니다. 이 함수들은 모드를 새로
판정하지 않고, 전달된 탐지 결과를 기존 겹침 우선순위로 정리한 뒤 변환합니다.

```python
from ko_pii import detect_all, tokenize

source = "Email: demo@example.com"
detections = detect_all(source, include={"EMAIL"})
output, vault = tokenize(source, detections)
assert output == "Email: <EMAIL_1>"
assert vault.reveal("<EMAIL_1>") == "demo@example.com"
```

## 1.22.12부터 거부하는 입력

- 원문이 `str`가 아니거나 탐지 항목이 `DetectionResult`가 아닌 경우.
- `0 <= start < end <= len(source)`를 만족하지 않는 좌표. bool/float 좌표도 거부합니다.
- `detection.text != source[start:end]`인 경우. 탐지 후 앞부분을 붙이거나 잘라냈다면
  이전 좌표를 재사용하지 말고 최종 원문에서 다시 탐지하세요.
- 잘못된 위험도 타입, 유한하지 않거나 0~1 범위를 벗어난 신뢰도, 잘못된 메타데이터 타입.
- 비어 있거나 `<`, `>`, 줄바꿈이 들어간 라벨. 안전한 사용자 정의 라벨은 계속 허용합니다.

모든 탐지 항목을 먼저 검증하므로 뒤쪽 항목이 잘못되었거나 반복자가 중간에 실패해도
그 호출의 변환과 Vault 저장을 시작하지 않습니다. 일반 예외 메시지는 입력값을 포함하지
않는 `ValueError`이며, 반복자 예외의 기본 traceback 연결도 숨깁니다.
호출자가 작성한 코드 자체를 격리하거나 로그 출력을 막는 sandbox는 아닙니다.

반복자가 같은 가변 탐지 객체를 여러 번 재사용해도 각 yield 시점의 판단 필드와
메타데이터 컨테이너를 복사해 보존합니다. 임의 중첩 Python 객체 전체를 deep copy하거나
동시 변경을 동기화하는 계약은 아닙니다. 입력 사전 검사는 Vault 저장소의 실행 중 실패를
되돌리는 트랜잭션과도 다릅니다.

## 해시 길이와 호환성

`hashed(..., digest_len=12)`는 1~64의 정수만 받습니다. 0·음수·bool·범위 초과는
빈 해시나 묵시적 잘라내기로 처리하지 않습니다. 기본 12자(48비트)는 변경하지 않았습니다.
짧은 해시는 충돌 가능성이 높고 어떤 길이도 유일 식별자나 익명성 보장은 아닙니다.
지문은 Vault의 키·salt·scheme·반복 횟수 설정을 따르며, 신규 Vault는 PBKDF2를 사용합니다.
`hashed`는 복원용 Vault 항목을 만들지 않지만 메모리 지문 캐시에는 원문이 남을 수 있습니다.
해시 사용을 메모리상의 원문 삭제로 해석하지 마세요. 자세한 경계는 [Vault 보안](VAULT_SECURITY.md)에 있습니다.

기존 정상 입력의 출력, 토큰 재사용, 원문 복원, 사용자 정의 라벨은 유지합니다.
1.22.11 이하에서 조용히 처리되던 잘못된 입력이 이제 오류로 중단될 수 있습니다.
`Anonymizer`의 탐지 규칙·임계값·정상 출력은 이 변경으로 확장하지 않습니다.
