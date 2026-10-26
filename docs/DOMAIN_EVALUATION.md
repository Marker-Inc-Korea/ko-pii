# 내 문서로 탐지 성능 확인하기

`ko-pii-evaluate`는 직접 정답을 표시한 문서의 라벨별 정탐(TP), 오탐(FP), 미탐(FN)을
계산합니다. 패키지 업데이트나 PERSON 제외 목록 변경 전후를 같은 문서로 비교할 수 있습니다.
모델 호출이나 외부 전송은 없습니다.

## 빠른 실행

저장소에 포함된 예제는 사용법 확인을 위한 합성 문서이며 성능 벤치마크가 아닙니다.

```bash
python -m pip install --upgrade ko-pii
ko-pii-evaluate docs/examples/domain-evaluation.jsonl \
  --labels PHONE,PERSON,RRN --output baseline.json

# 패키지 또는 정책을 변경한 뒤 같은 문서로 비교
ko-pii-evaluate docs/examples/domain-evaluation.jsonl \
  --labels PHONE,PERSON,RRN --baseline baseline.json \
  --output current.json --fail-on-new-misses
```

예제를 내려받지 않았다면 아래 JSONL 형식으로 자신의 평가 파일을 준비합니다.
CLI는 `python -m ko_pii.eval.domain`으로도 실행할 수 있습니다.

## 입력 형식

UTF-8 JSONL의 한 줄이 문서 하나입니다. `id`, `text`, `spans`를 모두 지정합니다.

```json
{"id":"sample-001","text":"010-1234-5678","spans":[{"label":"PHONE","start":0,"end":13}]}
{"id":"sample-002","text":"성명: 김도구","spans":[{"label":"PERSON","start":4,"end":7}]}
{"id":"sample-003","text":"system ready","spans":[]}
```

- `start`는 시작 위치, `end`는 끝 다음 위치입니다. Python 문자열의 문자 인덱스이며
  바이트나 JavaScript UTF-16 인덱스가 아닙니다.
- 평가할 라벨의 **모든 출현 위치**를 표시해야 합니다. 정답 누락은 오탐으로 계산됩니다.
- `--labels`를 생략하면 ko-pii 전체 라벨을 평가합니다. 전화번호만 표시했다면
  `--labels PHONE`을 지정해야 다른 개인정보를 오탐으로 잘못 계산하지 않습니다.
- 문서 ID는 중복될 수 없습니다. ID에는 고객 이름이나 주민번호 대신 불투명한 번호를 씁니다.
- 빈 데이터셋, 잘못된 라벨·범위, 중복 span은 오류입니다. 음성 예제는 `spans: []`로
  포함할 수 있지만, 양성 예제가 없으면 재현율은 `null`/`n/a`입니다.
- 입력 상한은 UTF-8 16 MiB, 10,000문서, 문서당 100,000문자와 2,000 span입니다.

## 결과 읽기

콘솔에는 라벨별 TP/FP/FN, precision, recall을 표시합니다. JSON 보고서는 전체 지표,
문서별 정답·예측 위치, 미탐·오탐 위치, 데이터셋 해시, 버전과 평가 라벨을 담습니다.
원문이나 실제 검출 문자열은 보고서에 복사하지 않습니다. 문서 ID와 위치·라벨도 내부
정보일 수 있으므로 보고서를 공개하기 전 확인하십시오.

매칭은 라벨과 시작·끝 위치가 모두 같은 **strict span** 방식입니다. 조사 한 글자를
더 포함해도 불일치로 계산됩니다. 따라서 이 명령의 미탐은 정답 span과의 불일치이며,
가명화 결과에서 실제 개인정보가 얼마나 남았는지를 직접 측정하는 수치는 아닙니다.

전체 점수만 보지 말고 목적에 필요한 라벨의 FN과 원문 위치를 확인하십시오. 정답 표시와
표본 구성이 잘못되면 결과도 의미가 없습니다. 이 명령은 운영 승인이나 법적 익명성 판정은
수행하지 않습니다.

## 조건별 집계와 출처 고정

1.22부터 각 JSONL 문서에 `"metadata":{"domain":"form","variant":"fullwidth"}`를
선택적으로 추가할 수 있습니다. `domain`과 `variant`는 각각 최대 128종의 짧은 분류명이며
키 값에는 이름/주소 같은 원문을 넣지 마세요. 값은 64자 이내의 문자·숫자·밑줄·점·하이픈만
허용합니다. 누락된 분류는 `null` 그룹으로 집계합니다. 분류 자체를 자동 추측하지 않습니다.

```bash
ko-pii-evaluate docs/examples/evaluation-slices.jsonl --labels PHONE \
  --output-mode STRICT --output-strategy redact --output slices.json
```

이 6건은 전각/zero-width/하이픈 제거/조사/음성 예제의 **합성 회귀 확인용**이며
독립 외부 성능 벤치마크가 아닙니다. 보고서의 `slices.domain`과 `slices.variant`에는
문서 수, TP/FP/FN, 라벨별 precision/recall/F1, 선택한 경우 출력 잔존 집계가 있습니다.
문서별 F1 평균이 아니라 카운트를 합산합니다. 정답이 없는 그룹의 recall은 `null`이며
두 분류 차원의 문서가 중복되므로 차원 간 수치를 합산하지 않습니다.

분류 배정은 데이터셋 해시에 포함합니다. 같은 텍스트라도 분류를 바꿨다면 이전 보고서와
직접 회귀 비교하지 않습니다. 기존 metadata 없는 파일의 해시 형식은 유지합니다.
K-PII-Bench 어댑터도 원본의 명시적 `domain`/`variant`를 보존하며 파일명으로 추측하지
않습니다. `template_id` 같은 개별 식별자별 통계는 이번 버전에서 만들지 않습니다.

외부 데이터의 수정 전후를 혼동하지 않으려면 로컬 manifest를 함께 둡니다.

```json
{"schema_version":1,"source_sha256":"실제-JSONL-파일의-64자리-SHA256","revision":"고정한-commit-id","split":"test-shard-01"}
```

```bash
sha256sum my-documents.jsonl
ko-pii-evaluate my-documents.jsonl --provenance manifest.json --output report.json
```

위 해시 자리에 첫 명령으로 확인한 실제 값을 적습니다. 평가는 한 번 읽은 UTF-8 입력
스냅샷을 사용하며 원본의 정확한 SHA-256이 다르면 보고서 쓰기 전에 실패합니다.
`revision`/`split`은 호출자의 선언이고 GitHub에 접속해 검증한 값이 아닙니다.
보고서에 `upstream_revision_verified: false`를 명시하며 서로 다른 provenance의
baseline 비교는 거부합니다. 데이터 다운로드·라이선스 확인·정답 품질 보증은 하지 않습니다.

## 최종 출력도 확인하기

1.18부터 정답으로 표시한 구간과 실제 치환 좌표를 대조할 수 있습니다.

```bash
ko-pii-evaluate my-documents.jsonl --labels PHONE,PERSON \
  --output-mode STRICT --output-strategy redact \
  --fail-on-retained --output output-check.json
```

탐지기를 출력에 다시 실행하는 방식이 아닙니다. 실제 `Anonymizer`가 생성한 치환 전후
좌표와 출력 구간을 사용합니다. `output_evaluation`은 다음 상태를 구분합니다.

- `replaced`: 정답 구간 전체에 치환이 적용됐고 대응 출력 구간에 같은 원문 전체가 남지 않음.
- `missed`: 해당 정답 구간에 겹치는 탐지 결과와 치환이 없음.
- `retained_by_policy`: 탐지했지만 REVIEW/ALLOW 또는 AUDIT 정책 등으로 치환하지 않음.
- `partially_replaced`: 정답 구간의 일부만 치환함.
- `partial_strategy`: partial 전략으로 일부 정보 보존을 의도함. 전체 제거로 계산하지 않음.
- `literal_retained`: 치환은 적용됐지만 대응 출력에 원문 전체가 그대로 포함됨.

`--fail-on-retained`는 `replaced`가 아닌 정답 구간이 하나라도 있으면 보고서를 저장한 뒤
종료 코드 1을 반환합니다. 의도된 partial 전략도 이에 포함됩니다. 정답이 0건이면 이 검사도
검사 대상이 0건인 것이지 안전성을 입증한 것이 아닙니다.

이 평가는 입력 JSONL의 텍스트·선택 라벨·정답 구간에 한정됩니다. 정답에서 누락된 개인정보,
문서 추출에서 빠진 영역, 재식별 가능성, 토큰/Vault 보안은 별도 검증이 필요합니다.
`replaced`도 철자 변형·의미적 복원 가능성이나 법적 익명성을 보장하지 않습니다.
부분 마스킹이나 FPE와 같은 전략의 유지 정보가 용도에 적합한지는 별도 판단해야 합니다.

`--baseline` 비교와 `--fail-on-new-misses`는 계속 **탐지 span만** 비교합니다.
출력 검사는 현재 실행의 절대 조건이며 이전 실행 대비 출력 회귀 검사가 아닙니다.
보고서는 mode/strategy와 상태·좌표만 담고 원문과 실제 치환 문자열은 복사하지 않습니다.

## 업데이트 전후 비교

```bash
ko-pii-evaluate my-documents.jsonl --labels PHONE,PERSON \
  --person-exclusions-file proposed-exclusions.txt \
  --baseline baseline.json --output proposed.json \
  --fail-on-new-misses --fail-on-new-false-positives
```

`new_false_negatives`는 이전에 잡았지만 이번에 놓친 항목이고,
`resolved_false_negatives`는 이전 미탐 중 이번에 잡은 항목입니다. 오탐도 같은 방식으로
분리합니다. 다른 오류를 고쳐 전체 F1이 유지됐더라도 새로 생긴 미탐을 숨기지 않습니다.

비교는 같은 문서·정답·평가 라벨·매칭 방식에만 허용합니다. 데이터셋을 바꾸면 새 기준
보고서를 만들어야 합니다. 문서 순서만 바뀐 경우는 비교할 수 있습니다.
PERSON 제외 목록과 패키지 버전은 비교 대상이므로 서로 달라도 됩니다.

종료 코드:

- `0`: 평가 완료, 지정한 회귀 조건에 해당하지 않음. 정확도 합격을 뜻하지 않습니다.
- `1`: 지정한 새 미탐/오탐 조건에 해당함. 결과 JSON은 저장됩니다.
- `2`: 입력·기준 보고서·출력 경로 오류. 비교 결과를 만들지 않습니다.

이전 릴리스에 평가 명령이 없으면 먼저 현재 버전에서 기준 보고서를 만들고, 다음 변경부터
비교합니다. 예전 패키지를 새 버전이라고 표시하거나 결과를 추정해서 채우지 않습니다.
