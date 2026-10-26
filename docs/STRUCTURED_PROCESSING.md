# 구조화 입력, 혼합 정책, 설명 보고서

이 문서는 `1.20.0`에 추가된 API를 설명합니다. 이전 버전에서는 사용할 수 없으므로
설치 버전을 확인하십시오. 코어 외부 의존성은 추가하지 않았습니다.

## 문자열에 종류별 정책 적용

```python
from ko_pii import Anonymizer
from ko_pii.reporting import explain

anon = Anonymizer(
    strategy="tokenize",
    strategies={"RRN": "redact", "PHONE": "partial"},
    include=["RRN", "PHONE", "EMAIL"],
)
result = anon.process("주민번호 880101-1234568 연락처 010-2345-6789 메일 user@example.com")
print(result.text)
# 주민번호 [주민등록번호] 연락처 010-****-6789 메일 <EMAIL_1>
print(explain(result))
```

`strategy`는 기본값이고 `strategies`의 라벨별 설정이 우선합니다. 탐지와 겹침 판정은
한 번 수행하며 실제 치환을 같은 계획에서 적용합니다. 모르는 라벨/전략은 오류입니다.
이 설정은 처리 모드의 임계값을 바꾸지 않습니다. REVIEW/ALLOW는 그대로 남고 AUDIT는
변환하지 않습니다. 일부 가림은 정보 전체 제거가 아닙니다.

## 중첩 JSON

```python
from ko_pii import Anonymizer, anonymize_json

payload = {
    "users": [{"email": "user@예시.kr", "phone": "010-2345-6789", "count": 3}],
    "enabled": True,
}
processed = anonymize_json(
    payload,
    anonymizer=Anonymizer(strategy="redact", strategies={"PHONE": "partial"}),
)
print(processed.data)
# {'users': [{'email': '[이메일]', 'phone': '010-****-6789', 'count': 3}], 'enabled': True}
print(processed.report())  # 원문과 경로를 포함하지 않는 처리 메타데이터
```

입력 객체는 수정하지 않고 새 객체를 반환합니다. 문자열 값을 재귀적으로 탐지하며
일반 숫자, 불리언, null은 보존합니다. 키는 가리지 않습니다. 키 자체가 이메일인 객체나
일반 숫자 필드의 식별자까지 처리됐다고 해석하면 안 됩니다.

`processed.fields`는 JSON Pointer와 일반 `AnonymizationResult`를 담은 내부 검토용
목록입니다. 원문/Vault를 포함할 수 있으므로 통째로 로그에 기록하지 마십시오.
`processed.report(include_paths=True)`도 키에 담긴 개인정보를 노출할 수 있습니다.

### 필드 전체의 라벨을 명시

```python
result = anonymize_json(
    {"customer": {"name": "이상", "account": 12345}},
    anonymizer=Anonymizer(strategy="redact"),
    field_labels={"/customer/name": "PERSON", "/customer/account": "ACCOUNT"},
)
assert result.data == {"customer": {"name": "[성명]", "account": "[계좌번호]"}}
```

이것은 필드명 자동 추측이 아니라 호출자의 **명시적 라벨 단언**입니다. AUDIT 이외
모드에서는 해당 필드 전체를 변환합니다. 정수 식별자는 변환되면 문자열이 됩니다.
null은 유지하고, 부동소수점/불리언/객체/배열을 식별자로 단언하면 오류입니다.
AUDIT에서는 정수 타입도 원래대로 유지합니다. 필드 매핑이 include/exclude와 충돌하거나
문서에 존재하지 않으면 오류로 처리합니다.

경로는 정확한 JSON Pointer만 지원합니다. `~`는 `~0`, `/`는 `~1`로 이스케이프하며,
배열 원소는 `/users/0/email`처럼 지정합니다. 빈 경로 `""`는 루트 값입니다.
정확한 Pointer 안의 `*`는 와일드카드가 아닙니다. 경로별 전략 override는 지원하지 않습니다.

### 반복 배열과 선택 필드

```python
from ko_pii import Anonymizer, EACH, FieldRule, anonymize_json

result = anonymize_json(
    {"users": [{"name": "이상", "phone": "018-2345-6789"}, {"name": "김도구"}]},
    anonymizer=Anonymizer(strategy="redact"),
    field_rules=[
        FieldRule(("users", EACH, "name"), "PERSON"),
        FieldRule(("users", EACH, "phone"), "PHONE", required=False),
    ],
)
assert result.data["users"][0]["name"] == "[성명]"
assert result.field_rule_summary[1]["missing"] == 1
```

경로의 문자열은 객체 키, 정수는 배열 인덱스, `EACH`는 배열의 모든 원소입니다.
`"*"`라는 실제 키와 혼동하지 않습니다. 최대 128개 규칙, 규칙당 최대 128개 경로 조각을
허용합니다. 규칙끼리 또는 `field_labels`와 다른 라벨을 같은 위치에 지정하면 오류입니다.

`required=False`는 키/인덱스가 **없는 경우만** 허용합니다. 배열 자리에 객체가 있거나
중간 부모가 null인 경우 등 타입 불일치는 건너뛰지 않습니다. 마지막 값의 null은 보존하고
`null_fields`로 집계합니다. 빈 배열은 오류 없이 `empty_arrays`에 기록합니다. 빈 배열을
허용하지 않아야 한다면 호출자가 별도로 검사해야 합니다. `matched`는 발견한 필드 수이지
실제 치환 수가 아닙니다. 규칙이 지정되지 않은 문자열 값도 일반 탐지로 처리합니다.

`report()["field_rules"]`에는 규칙 번호와 라벨, matched/missing/empty_arrays/null_fields만
기록하며 값과 키 경로는 기본 출력하지 않습니다. 기존 정확한 `field_labels`는 여전히
필수 경로이며, 규칙 설정은 필드명 자동 추측이 아닙니다.

### JSONL

```python
from ko_pii import anonymize_jsonl

rows = anonymize_jsonl('{"message":"user@example.com"}\n{"message":"user@example.com"}\n')
assert rows[0].source_line == 1
assert rows[1].source_line == 2
```

빈 행은 건너뛰지만 입력 전체가 비어 있으면 오류입니다. 레코드는 LF로 구분하며
문자열 내부의 Unicode 줄 구분자를 새 레코드로 취급하지 않습니다. 한 호출은 공통
Anonymizer/Vault를 사용하므로 같은 값은 레코드 사이에서도 같은 토큰이 됩니다.
레코드 간 연결을 원하지 않으면 레코드마다 별도 Anonymizer/Vault로 호출하십시오.

전체 입력의 문법, 키 중복, 필드 매핑을 먼저 검증합니다. 처리 단계에서 사용자 탐지기나
감사 저장소가 실패하면 이미 메모리 Vault에 저장된 값까지 되돌리는 트랜잭션은 제공하지
않습니다. 결과는 부분 반환하지 않습니다.

## 입력 한도와 오류

`StructuredLimits` 기본값은 깊이 64, 문서당 노드 100,000개, 입력 문자열 10,000,000자,
문자열 값/키당 1,000,000자, JSONL 문서 10,000개입니다. 깊이는 최대 128까지 설정할 수
있습니다. CLI는 기존 `--max-file-bytes`, `--max-text-chars`도 적용합니다.

엄격한 파서는 `loads_json()`입니다. 이미 `json.loads()`로 읽은 객체의 원래 중복 키나
float 정밀도 손실은 복구할 수 없습니다. JSON 텍스트는 가급적 이 파서로 읽으십시오.
순환, NaN/Infinity, 고립 surrogate, 비JSON 타입은 거부합니다. 오류 메시지에 원문 값이나
키를 재출력하지 않습니다. 완전한 메모리/CPU 샌드박스를 제공하는 API는 아닙니다.

## CLI

```bash
ko-pii input.json --format json --strategy redact \
  --strategy-for PHONE=partial \
  --field-label /customer/name=PERSON \
  --output masked.json --explain decisions.json --json-summary

ko-pii input.jsonl --format jsonl --strategy redact --output masked.jsonl

ko-pii docs/examples/structured-array-input.json --format json \
  --field-rules docs/examples/field-rules.json --strategy redact \
  --output masked-array.json --json-summary

ko-pii input.txt --strategy tokenize --strategy-for RRN=redact \
  --report certificate.txt --explain decisions.json
```

JSON 모드는 파일 내용을 정규화해 JSON 문법을 바꾸지 않고, UTF-8 원문을 읽은 뒤 값만
처리합니다. UTF-8 BOM은 파일 입력에서 허용합니다. 입력/출력/Vault/보고서 파일 경로가
같으면 거부합니다. 파일 출력은 성공한 결과를 atomic replace로 저장합니다. stdout과
Vault, 보고서까지 하나의 파일시스템 트랜잭션으로 묶이지는 않습니다.

새 정책/구조화/설명 옵션은 현재 단일 파일 모드용입니다. `--batch`와 조합하면 조용히
무시하지 않고 오류로 처리합니다. JSON 보고서는 `--report` 대신 `--explain`을 사용합니다.

`--field-rules` 설정 파일에서는 경로 배열의 null이 `EACH`를 뜻합니다:

```json
[
  {"path": ["users", null, "name"], "label": "PERSON"},
  {"path": ["users", null, "phone"], "label": "PHONE", "required": false}
]
```

설정 파일도 출력으로 덮어쓰지 못하며 입력 한도와 엄격한 JSON 검증을 적용합니다.
JSONL은 모든 행의 필드 규칙과 타입을 먼저 검사한 뒤 변환합니다.

## 정책 변경 미리보기

```python
from ko_pii.policy_preview import compare_policies

preview = compare_policies(
    "018-2345-6789 user@example.com",
    before={"include": ["PHONE", "EMAIL"], "strategies": {"PHONE": "partial"}},
    after={"include": ["PHONE", "EMAIL"], "strategies": {"PHONE": "redact"}},
)
assert preview["changed_by_label"] == {"PHONE": 1}
```

```bash
ko-pii-compare-policies docs/examples/policy-input.txt \
  --before docs/examples/policy-before.json \
  --after docs/examples/policy-after.json --output policy-preview.json
```

허용 설정은 mode/strategy/strategies/include/exclude/person_exclusions입니다. 각 설정을
독립된 메모리 Vault에서 실행하며 기존 Vault, 감사 저장소, 모델 어댑터를 받지 않습니다.
사용자의 입력/설정 파일은 바꾸지 않고 지정한 보고서만 저장합니다. 기본은 UTF-8 평문
미리보기이며 API 입력 100,000자, 관측 위치 2,000개 한도입니다. CLI는 파일당 400,000바이트
한도도 적용합니다. 원문만 `-`로 표준 입력을 받을 수 있고 설정은 JSON 파일이어야 합니다.

보고서 계약은 `ko-pii-policy-preview-v1`입니다. 라벨·위치별로 탐지 여부, 처리 동작,
requested_strategy/applied_strategy와 실제 출력 잔존 상태를 비교합니다. 랜덤 토큰 자체는
비교하지 않으며 원문/치환값/설정 원문은 보고서에 포함하지 않습니다. 설정 해시와 위치도
메타데이터이므로 무조건 공개해도 된다는 뜻은 아닙니다.

**두 정책 중 하나가 탐지한 위치의 합집합만** 비교합니다. 둘 다 놓친 개인정보는 비교할 수
없으며 정확도/익명성을 판정하지 않습니다. `not_detected`는 해당 정책에서 그 위치가
탐지되지 않았다는 뜻입니다. `replaced`도 원문 범위의 치환이지 재식별 불가능 판정은 아닙니다.
AUDIT처럼 치환하지 않은 결과는 applied_strategy가 null입니다. 정확도와 코드 회귀는 별도의
정답 라벨을 가진 `ko-pii-evaluate`로 확인하십시오.

### JSON 필드별 정책 미리보기

1.22에서 추가했습니다. `python -m pip install --upgrade ko-pii`로 설치합니다.
기존 설정 객체와 `PolicyProfile`/프로필 JSON을 모두 사용할 수 있습니다.

```python
from ko_pii.policy_preview import compare_json_policies

before = {"include": ["PERSON"], "field_labels": {"/customer": "PERSON"}}
after = {**before, "field_person_exclusions": {"/product": ["홍길동"]}}
preview = compare_json_policies(
    {"product": "성명: 홍길동", "customer": "홍길동"}, before=before, after=after,
)
assert preview["changed_by_label"] == {"PERSON": 1}
assert preview["changes"][0]["after"]["output_state"] == "not_detected"
assert preview["fields"][1]["after_output_counts"] == {"replaced": 1}
```

상품 필드의 제외어만 바뀌며 고객 필드의 명시적 PERSON 단언은 유지됩니다.
제외어 추가는 개인정보 제거 강화가 아니라 탐지 감소일 수 있음을 보고서로 확인합니다.

```bash
ko-pii-compare-policies docs/examples/policy-json-input.json --format json \
  --before docs/examples/policy-json-before.json \
  --after docs/examples/policy-json-after.json --output /tmp/ko-pii-json-preview.json
```

기존 코어 설정에 `field_labels`, `field_rules`, `field_person_exclusions`를 추가로
받습니다. Python API의 `field_rules`도 JSON 설정 형태의 목록을 사용합니다.
예를 들어 `{"path": ["users", null, "id"], "label": "ACCOUNT", "required": false}`는
배열의 존재하는 id 필드만 단언합니다. Python에서는 `null`/`false` 대신 `None`/`False`입니다.
누락된 필수 경로, 잘못된 라벨, include/exclude와 충돌하는 단언은 오류입니다.

보고서 계약은 `ko-pii-structured-policy-preview-v1`입니다. 실제 `anonymize_json` 결과를
비교하고 각 설정에 새 메모리 Vault를 사용합니다. 필드별/전체 관측 건수와 변경 건수를
제공하며 원문, 치환값, 설정 원문은 포함하지 않습니다. 키/경로도 기본 제외합니다.
`include_paths=True` 또는 `--include-paths`는 민감한 JSON 키를 그대로 노출할 수 있습니다.

`field_index`는 입력 순서의 모든 문자열/정수 잎을 기준으로 한 0부터 시작하는 번호입니다.
양쪽 모두 처리하지 않은 정수는 보고 행에서 빠져 번호에 빈 구간이 생길 수 있습니다.
단언이 한쪽에만 있는 정수는 `before_screened`/`after_screened`로 구분하며 처리하지 않은
쪽의 `not_detected`는 검사 후 개인정보가 없다는 뜻이 아닙니다. 좌표는 각 필드 안의
Python 문자 위치이고 정수 단언에는 십진 문자열 기준을 사용합니다.
키, 일반 숫자, bool/null, 양쪽 모두 놓친 문자열의 안전성은 평가하지 않습니다.

단일 JSON 값만 지원하며 JSONL 비교는 지원하지 않습니다. 최대 깊이 64, 노드 10,000개,
키/값/정수 문자열 합계 100,000자, 문자열/정수 잎 1,000개, 전체 관측 위치 2,000개입니다.
CLI는 직렬화된 입력과 각 설정 파일에도 400,000바이트/100,000자 한도를 적용합니다.
순환 객체, 중복 JSON 키, 비유한 수, 잘못된 Unicode를 거부합니다.
한도 초과를 부분 성공으로 보고하지 않으며 실패 시 기존 입력과 보고서는 바꾸지 않습니다.

## 보고서 계약과 민감 정보

`explain(result)`의 계약 이름은 `ko-pii-explanation-v1`, schema_version은 1입니다.
`source_span`, `output_span`은 Python Unicode code-point의 반열린 구간입니다.
`rule_id`는 탐지기 계열 ID이며 모든 내부 정규식의 ID는 아닙니다. 알 수 없는 외부
탐지기의 ID는 null입니다. `normalized`는 정규화 경로를 통해 원문으로 역매핑했음을 뜻합니다.
문서 전체에 정규화가 적용돼 값 자체가 바뀌지 않은 탐지도 이 경로를 탈 수 있습니다.

`checks`에는 허용된 검사 코드만 포함하고, 자유 형식 `evidence`와 `extra`는 복사하지
않습니다. `requested_strategy`와 `applied_strategy`를 구분하며, REVIEW/ALLOW나 실제
치환되지 않은 항목의 applied_strategy는 null입니다. confidence는 교정된 확률이 아닙니다.

겹침 해소 후 선택된 탐지만 보고합니다. 버린 후보의 전체 이력, 미탐지 원인의 추정,
데이터가 법적으로 익명이라는 판정을 만들어 내지 않습니다. 이 보고서도 위치·건수 등의
메타데이터를 포함하므로 모든 상황에서 무해한 공개 자료라는 뜻은 아닙니다.

### 처리 증명서의 기본값 변경

`generate_certificate()`는 이제 원문, 치환값, 문서 식별자를 기본적으로 출력하지
않습니다. 원문을 보는 내부 검토 화면이라면 다음을 명시적으로 선택할 수 있습니다.

```python
from ko_pii.reporting import generate_certificate

internal_report = generate_certificate(
    result,
    document_id="internal-document-id",
    include_review_details=True,
    include_document_id=True,
    include_replacements=True,
)
```

이 결과는 외부 공유용이 아닙니다. CLI `--report-include-sensitive`도 같은 선택입니다.
기존 원문 표시용 HTML 보고서, `result.detections`, Vault는 계속 민감한 객체입니다.

## 외부 평가와 출력 잔존 회귀

외부 데이터는 자동으로 받지 않습니다. 별도로 확보한 K-PII-Bench의 JSONL 부분집합을
기존 평가기에 전달할 수 있습니다. 16 MiB / 10,000문서 한도를 유지하므로 큰 split은
고정된 방법으로 분할해야 합니다. 일부만 평가하고 전체 split 결과처럼 발표하지 마십시오.

```bash
ko-pii-evaluate local-test-subset.jsonl --dataset-format k-pii-bench \
  --labels EMAIL,PHONE,RRN --output-mode STRICT --output baseline.json

ko-pii-evaluate local-test-subset.jsonl --dataset-format k-pii-bench \
  --labels EMAIL,PHONE,RRN --output-mode STRICT --baseline baseline.json \
  --fail-on-new-misses --fail-on-new-false-positives --fail-on-new-retained \
  --output current.json
```

매핑하지 않는 USERNAME/ORGANIZATION/NRP/PERSONAL_ATTRIBUTE는 별도 건수로 기록합니다.
KR_LOCATION을 ADDRESS로 정렬하는 것도 평가 정책이지 두 개념이 완전히 같다는 보장은
아닙니다. 원문 `surface`와 offset이 다르면 해당 레코드를 자동 보정하지 않고 거부합니다.
source hash와 adapter version, label map을 기록하며, 같은 데이터/정책끼리 비교합니다.
기존 ko-pii strict character-span 점수를 쓰므로 upstream BIO 점수와 직접 비교하지 마십시오.

`--output-strategy-for PHONE=partial`로 혼합 정책도 평가할 수 있습니다. `--fail-on-retained`는
의도한 partial도 실패로 보고, `--fail-on-new-retained`는 같은 정책에서 전에는 완전히
치환됐던 gold span이 새로 남는 경우만 실패로 봅니다. 탐지 비교와 실제 출력 비교는 별도입니다.

출처: [K-PII-Bench](https://github.com/woohyun212/k-pii-bench),
[공개 데이터 카드](https://huggingface.co/datasets/woohyun212/k-pii-bench).
코드와 데이터의 라이선스를 구분해야 하며, 이 저장소에는 외부 평가 데이터를 재배포하지 않습니다.

## 탐지 보완의 범위

한글 중간 도메인과 ASCII 최종 도메인의 이메일(`user@예시.kr`)을 지원합니다.
Unicode local-part, Unicode 최상위 도메인, 모든 국제화 이메일 문법까지 지원한다는
뜻은 아닙니다. IDNA 인코딩은 형식 확인이지 DNS/메일함 실재 확인이 아니며 네트워크를
호출하지 않습니다.

`MODEL010-2345-6789CODE` 같은 제품 식별자의 부분 문자열은 보수적으로 계속 탐지할
수 있습니다. 영문 인접 번호를 일괄 제외하면 `TEL010-2345-6789` 같은 연락처도 놓치므로
이번에는 해당 잔여 오탐을 숨기거나 전역 경계 규칙으로 제거하지 않았습니다.
