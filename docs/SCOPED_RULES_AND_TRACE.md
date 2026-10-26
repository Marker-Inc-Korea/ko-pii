# 필드별 제외, 사용자 정의 규칙, 설명 추적

1.21.0에서 추가된 기능입니다. `python -m pip install --upgrade 'ko-pii>=1.21.0'`으로 설치합니다.
소스에서 사용하려면 소스 디렉터리에서 `python -m pip install -e .`를 실행합니다.
서버, OCR, 분류기 또는 새 런타임 의존성을 추가하지 않습니다.

## 1. 필드에 한정한 PERSON 제외

```python
from ko_pii import Anonymizer, anonymize_json

data = {"product": "홍길동", "customer": "홍길동", "mail": "user@example.com"}
result = anonymize_json(
    data,
    anonymizer=Anonymizer(strategy="redact"),
    field_person_exclusions={"/product": ["홍길동"]},
    field_labels={"/customer": "PERSON"},
)
assert result.data == {"product": "홍길동", "customer": "[성명]", "mail": "[이메일]"}
```

- 정확한 JSON Pointer만 사용합니다. `/items/0/product`는 첫 항목만 선택합니다.
  `*`는 와일드카드가 아닙니다. `/`가 든 키는 `~1`, `~`가 든 키는 `~0`로 표현합니다.
- 제외어는 정규화한 PERSON 후보와 정확히 일치할 때만 적용합니다. 부분 문자열/정규식
  제외는 하지 않습니다. 전화·주민번호·이메일 등 다른 라벨은 제외되지 않습니다.
- 기존 `Anonymizer(person_exclusions=...)`는 여전히 인스턴스 전체에 적용됩니다.
  필드별로만 제한하려면 전역 제외에 넣지 말고 위 설정만 사용하세요.
- `field_labels`와 `FieldRule`은 필드 전체에 대한 명시적 개인정보 단언입니다.
  전역/필드별 제외어로 이를 우회할 수 없습니다. AUDIT 모드의 원문 보존은 유지합니다.
- 원본 객체와 Anonymizer 설정은 바꾸지 않으며 같은 Vault를 계속 사용합니다.
- 최대 128개 경로, 경로당 256개 제외어, 제외어당 256자입니다. 빈 제외어는 거부합니다.
  존재하는 문자열/null 필드만 지정할 수 있습니다. 잘못된 경로/타입은 조용히 무시하지 않습니다.
- JSONL에서도 같은 인수를 사용합니다. 모든 레코드에 해당 경로가 존재해야 하며,
  전체 입력/경로를 선검증한 뒤 처리합니다. 선택 경로와 배열 와일드카드는 이 제외 기능의
  범위가 아닙니다. 외부 탐지기 실패 시 전체 Vault 트랜잭션을 보장하지는 않습니다.
- 제외어는 탐지를 줄이는 정책입니다. 실제 인명과 같은 용어를 제외하면 그 필드에서는
  미탐이 생길 수 있습니다. 별도 라벨링 사례로 영향과 미탐을 함께 확인하세요.

CLI 설정 파일 `field-exclusions.json`:

```json
{"/product": ["홍길동"]}
```

```bash
ko-pii input.json --format json --strategy redact \
  --field-person-exclusions field-exclusions.json \
  --field-label /customer=PERSON -o output.json
```

저장소에 있는 합성 예제로 바로 확인하려면:

```bash
ko-pii docs/examples/scoped-fields.json --format json --strategy redact \
  --field-person-exclusions docs/examples/person-exclusions.json \
  --field-label /customer=PERSON --explain /tmp/ko-pii-scoped-explain.json --trace-limit 20
```

키와 JSON Pointer 자체가 개인정보일 수 있어 설명 보고서는 경로/제외어를 기본 출력하지 않습니다.
설정 파일은 공유 대상에서 제외하세요. 잘못된 경로는 실제 값을 반사하지 않는 오류로 반환합니다.

## 2. 작은 사용자 정의 탐지기

애플리케이션에 이미 있는 패턴을 연결하는 도우미입니다. 자동 규칙 학습, 별도 라벨 체계,
플러그인 설치 서버는 아닙니다. 기존 `secondary_detector` 병합 방식/처리 정책을 그대로 따릅니다.

```python
from ko_pii import Anonymizer, RegexDetector

# 예시: 사내 식별자를 기존 ACCOUNT 처리 정책에 연결합니다.
# 이 매핑은 애플리케이션의 정책 선택이며 새로운 법적 분류를 뜻하지 않습니다.
custom = RegexDetector(r"사번: (?P<id>EMP-\d{4})", label="ACCOUNT", group="id")
anon = Anonymizer(strategy="redact", include=["ACCOUNT"], secondary_detector=custom)
assert anon.process("사번: EMP-1042").text == "사번: [계좌번호]"
```

함수도 연결할 수 있습니다:

```python
from ko_pii import CallableDetector, DetectionResult, RiskLevel

def local_rule(text):
    if text.startswith("ID:") and len(text) > 3:
        yield DetectionResult("ACCOUNT", text[3:], 3, len(text), RiskLevel.HIGH)

anon = Anonymizer(secondary_detector=CallableDetector(local_rule))
```

- 좌표는 정규화 전 입력 문자열의 Python 문자 인덱스입니다. `text[start:end]`와
  탐지값이 일치해야 하며 빈/음수/범위 밖 span, 미지원 라벨, 잘못된 위험도와 NaN/무한대
  신뢰도를 거부합니다. `RiskLevel` enum, 0~1 범위 confidence를 사용하세요.
- 기본 입력 한도 1,000,000자, 결과 한도 10,000개입니다. `max_chars`, `max_matches`로
  설정합니다. 한도/검증 실패를 탐지 0건으로 숨기지 않으며, 전체 출력 검증 후 yield합니다.
- 정규식은 기본 전체 매치를 사용합니다. `group`은 정수/이름 모두 가능하며, 매치하지 않은
  선택 그룹은 건너뛰고 실제로 매치한 빈 그룹은 오류로 처리합니다.
- 원문과 무관한 메타데이터 누출을 피하려고 이 래퍼는 결과의 label/text/span/risk/confidence만
  복사합니다. 자유 형식 evidence/extra/legal_basis/rule_id는 전달하지 않습니다.
  원문을 포함하는 객체 자체와 Vault는 여전히 민감합니다.
- 기존 필터, PERSON 제외, 병합 우선순위와 모드 임계값은 계속 적용됩니다.
  빈 `include=[]`는 기존처럼 설정 오류로 거부됩니다. 전체 라벨은 `include=None`을 사용합니다.
- **신뢰된 개발자가 작성한 코드/정규식 전용입니다.** 실행 시간 제한이나 샌드박스가 아닙니다.
  악성 정규식, 느리거나 멈추지 않는 함수, 외부 API 호출을 차단하지 않습니다.
  입력/결과 개수 제한은 이러한 실행 시간 문제를 해결하지 않습니다.

### 직접 연결한 탐지기의 검증 (1.22)

래퍼 없이 `detect(text)` 메서드가 있는 객체를 연결해도 Anonymizer에서 같은 핵심 검증을
수행합니다. 원문 span/값 불일치, 미지원 라벨, 잘못된 위험도/신뢰도, 잘못된 메타데이터
타입을 해당 문자열의 치환/Vault 저장 전에 거부합니다. 필터로 제외될 라벨이나 AUDIT
모드도 검증을 우회하지 않습니다. 탐지기 예외는 원문을 담지 않는 `ValueError`로 반환합니다.

직접 연결한 결과의 evidence/extra/rule_id 등 정상 메타데이터는 보존합니다.
각 결과와 최상위 evidence/extra 컨테이너를 복사하되 extra 안의 임의 객체까지 격리하는
기능은 아닙니다. 래퍼의 자유 형식 메타데이터 제거 동작은 그대로 유지합니다.
기본 입력/결과 수 제한은 위 래퍼의 기능이지 모든 직접 연결 탐지기의 공통 제한은 아닙니다.

`merge_mode` 오타와 `role_split_labels=["PESRON"]` 같은 미지원 라벨은 생성 시 오류가
발생합니다. `role_split_labels=None`은 기본 위임 라벨, `[]`는 위임 없음으로 유지합니다.
저수준 `merge_detections`도 설정을 검증하지만 원문 인수가 없으므로 span/값의 원문 일치
검사는 Anonymizer 경계에서 수행합니다.

실패한 한 번의 문자열 처리에서 라이브러리의 새 Vault 저장을 막는 것이며 전체 JSON/JSONL
롤백을 뜻하지 않습니다. 탐지기 자체의 부수 효과, 외부 호출, 무한 실행을 막는 샌드박스도
아닙니다. 신뢰한 어댑터만 연결하고 정규화한 결과는 원문 좌표로 역매핑해 반환하세요.

## 3. 값 없는 설명과 제한된 겹침 추적

```python
from ko_pii.reporting import explain

result = Anonymizer(include=["EMAIL"], trace_limit=100).process("user [at] example [dot] com")
report = explain(result, include_trace=True)
assert report["findings"][0]["subrule_id"] == "email.obfuscated.v1"
```

기존 `rule_id`는 탐지기 계열을 유지합니다. 추가 `subrule_id`는 현재 이메일의
`email.ascii.v1`, `email.korean_domain.v1`, `email.obfuscated.v1`만 식별합니다.
원문 좌표 역매핑과 보조 탐지기 병합 이후에도 해당 메타데이터를 유지합니다.
정의하지 않은 세부 규칙은 `null`이며 없는 근거를 추측하지 않습니다.

추적은 두 단계의 명시적 선택입니다:

1. `Anonymizer(trace_limit=100)`으로 수집합니다. 기본 0은 수집 안 함, 최대 1,000입니다.
2. `explain(result, include_trace=True)`로 내보냅니다. 기본 보고서는 추적을 넣지 않습니다.

`overlap_trace`에는 공통 겹침 처리의 단계별 후보/채택/탈락 수와, 탈락 후보 및 이를 막은
채택 후보 하나의 라벨/규칙/좌표를 넣습니다. 위험도, 신뢰도, 길이, 시작 위치, 입력 순서 중
어느 우선순위에서 밀렸는지 구분합니다. 해당 단계의 blocker가 이후 병합 단계에서도
최종 채택된다는 뜻은 아닙니다. 원문/토큰/임의 evidence/extra는 포함하지 않습니다.

제한을 넘으면 추가 이벤트를 보관하지 않고 `truncated`, `omitted_events`로 표시합니다.
집계는 계속하며 출력 잘림이 탐지/치환 결과를 바꾸지 않습니다. `overlap_trace: null`은
수집하지 않았다는 뜻입니다. 명시적 필드 단언은 탐지를 거치지 않아 추적이 없습니다.

추적은 모든 탐지 과정의 완전한 설명이 아닙니다. 각 탐지기 내부의 후보 필터,
PERSON 제외, include/exclude, 병합 정책의 후보 제거, 애초에 생성되지 않은 미탐은
기록하지 않습니다. 외부 모델의 판단 이유나 개인정보 부재를 증명하지도 않습니다.
좌표와 라벨만으로도 문서 구조가 드러날 수 있으므로 무조건 공개 가능한 로그는 아닙니다.

```bash
ko-pii input.txt --explain explanation.json --trace-limit 100 -o redacted.txt
```

JSON/JSONL은 문자열 필드마다 독립적으로 한도를 적용하며 전체 보고서의 합계 상한은 아닙니다.
Python에서는 `result.report(include_trace=True)`로 필드별 추적을 출력합니다.
설명 v1의 기존 필드는 유지하고 선택적 `overlap_trace`는 별도 `ko-pii-overlap-trace-v1`
계약으로 관리합니다. 새 필드에 엄격한 소비자는 스키마를 업데이트해야 합니다.

## 4. 개발용 생성형 회귀 테스트

```bash
python -m pip install -e '.[dev,file,security]'
python -m pytest -q tests/property --hypothesis-show-statistics
```

[Hypothesis](https://hypothesis.readthedocs.io/en/latest/reference/api.html)의 `given`과
재현 가능한 설정을 사용합니다. 각 속성당 최대 200개 사례를 생성하며 실패를 작은 입력으로
축소합니다. 실패 예시는 고정 회귀 사례로도 남깁니다. 테스트 전용 의존성이므로 일반 설치에는
추가되지 않습니다. 데이터셋 다운로드나 모델 호출은 없습니다.

검사는 원문/출력 좌표 보존, 이메일 문장 경계, Vault 왕복 및 토큰 충돌 방지,
겹침 알고리즘의 단순 참조 구현과의 일치, 필드 격리를 다룹니다. 실제 도메인 정확도,
새로운 모든 공격/문서 양식, 개인정보의 법적 익명성을 보장하는 벤치마크는 아닙니다.
