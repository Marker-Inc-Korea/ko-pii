# 이메일·Vault 업데이트

## 1.22.4: 명시적 EMAIL 필드의 복합 입력

표/JSON의 EMAIL 필드, `anonymize_value()`와 저수준 변환에 `partial` 또는 `fpe`를
적용할 때는 지원하는 단일 주소 형식만 도메인을 보존합니다. 주소 목록, 표시 이름,
주석 또는 그 밖의 미지원 형식은 필드 전체를 별표로 가립니다. 첫 번째 `@` 이후에
있는 두 번째 주소나 부가 정보를 원문으로 남기지 않습니다.

```python
from ko_pii.tabular import anonymize_value

value = "first@example.com;second@example.com"
masked, _ = anonymize_value(value, "EMAIL", strategy="partial")
assert masked == "*" * len(value)
```

일반 텍스트 탐지에서는 발견한 주소들을 각각 변환하는 기존 동작을 유지합니다.
복수 주소를 개별 부분 마스킹해야 한다면 호출자가 필드를 분리해 각각 처리하세요.
이 수정은 지원하지 않는 필드를 안전하게 처리하는 변경이며 이메일 탐지 범위 자체의
확대나 모든 주소 형식의 지원을 뜻하지 않습니다.

## 1.20.1: 이메일 앞의 일반 문장 보존

기본 Anonymizer와 detect_all은 난독화 이메일의 로컬 파트로 인접한 한 단어만
선택합니다. 이메일 앞의 영문 단어들을 합치거나 이전 줄까지 포함하지 않습니다.

```python
from ko_pii import Anonymizer

result = Anonymizer(strategy="redact", include=["EMAIL"]).process(
    "Please email john [at] example [dot] com."
)
assert result.text == "Please email [이메일]."
```

`[at]`, `(at)`, `[dot]`, `(dot)` 및 구분자 주변의 space/tab은 계속 탐지합니다.
일반 이메일과 한글 도메인 지원도 유지합니다. 숫자 식별자의 제로폭/제어문자 삽입 탐지는
계속 동작하며, 이메일의 줄 경계만 별도로 보존합니다.

## 로컬 파트 내부 공백은 모호하다

`hong gildong @ naver . com`에서 `hong`이 앞 문장의 단어인지 이메일의 일부인지
형식만으로 확정할 수 없습니다. 기본값은 `gildong @ naver . com`만 탐지하므로
`hong`이 남습니다. 모든 난독화 이메일을 완전히 가린다는 보장이 아닙니다.

입력이 이메일 필드라는 것을 아는 경우에는 구조화 API의 EMAIL 필드 지정으로
필드 전체를 처리하는 방법을 우선 고려하세요. 텍스트 탐지가 필요하고 산문이 없는
분리된 필드라면 저수준 탐지기에서 내부 space/tab 복원을 선택할 수 있습니다.

```python
from ko_pii.patterns.email import detect
from ko_pii.modes.tokenize import tokenize

text = "hong gildong @ naver . com"
masked, vault = tokenize(text, detect(text, allow_spaced_local=True))
assert masked == "<EMAIL_1>"
assert vault.reveal("<EMAIL_1>") == text
```

이 옵션은 저수준 email.detect에만 있습니다. Anonymizer/CLI의 기본 탐지는 바꾸지 않습니다.
산문에 적용하면 앞 단어까지 합칠 수 있으므로 전체 문서에 일괄 적용하지 마세요.
두 모드 모두 줄을 넘겨 이메일을 복원하지 않습니다. 줄바꿈으로 분할된 이메일은
일부만 탐지되거나 탐지되지 않을 수 있으므로 필드 단언 또는 별도 도메인 검증이 필요합니다.

## 손상된 Vault는 읽기를 중단한다

`<PHONE_1>` 항목의 label이 EMAIL인 파일은 기존에 읽힐 수 있었고, 이후 PHONE을
저장하면 새 토큰이 기존의 다른 원문을 가리킬 수 있었습니다. 이제 다음을 거절합니다.

- 토큰/라벨 불일치, 잘못된 번호 형식, 같은 label/original에 대한 중복 토큰.
- 잘못된 원문/위험도/offset/occurrences/extra 타입과 fingerprint 설정.
- JSON 중복 키 및 NaN/Infinity 같은 비유한 숫자.

로드 실패는 ValueError로 알리며 원본 파일을 덮어쓰거나 자동으로 복구하지 않습니다.
상위 애플리케이션은 이 오류를 무시하고 빈 Vault로 재시작하지 않아야 합니다.
정상 schema v1, fingerprint 정보가 없는 legacy 파일, 기존 salt와 정상 토큰 번호는
계속 지원합니다. fingerprint_iterations를 명시할 때는 1 이상의 정수를 사용하세요.
암호화 Vault도 복호화 이후 같은 매핑 검사를 적용합니다.

이 검사는 내부 일관성 검사입니다. 파일의 진위, 접근 권한, 악의적인 일관된 변조까지
검증하는 서명이나 인증 기능은 아닙니다. Vault 격리·접근제어 책임은 기존과 같습니다.
