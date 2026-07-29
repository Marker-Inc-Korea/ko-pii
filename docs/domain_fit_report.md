# ko-pii 도메인 적합성 및 운영 자격검증

기준일: 2026-07-29

## 결론

ko-pii는 한국 공공·업무 문서의 **구조적 PII 전처리 엔진**으로 설계됐다. 패키지
소프트웨어는 안정 상태지만, 공개 벤치마크만으로 고객 환경의 운영 적합성을 승인하지 않는다.

- 주민등록번호, 전화, 이메일, 카드처럼 형식·체크섬 신호가 강한 라벨과 PERSON, ADDRESS,
  POSITION처럼 문맥·도메인 의존성이 큰 라벨을 분리해 판단한다.
- 공공 문서, 대화, 뉴스, 의료 문서는 PII 등장 방식과 gold 정책이 다르다.
- 고객별 문서 분포, 활성 라벨, 오탐·미탐 비용과 가명화 전략을 고정한 뒤 별도
  qualification을 통과해야 한다.
- 이 도구는 법적 익명성 판정, 정보주체 권리 절차 또는 개인정보 영향평가를 대신하지 않는다.

## 현재 사용할 수 있는 증거

| 평가 | 문서 | 측정 목적 | ko-pii 결과 | 운영 해석 |
|---|---:|---|---:|---|
| KDPII test | 4,891 | 인간 라벨 대화체 | micro F1 0.660 | 대화형 분포 참고 |
| 생성 평가셋 | 540 | 행정·서식형 26라벨 | micro F1 0.790 | 대상 도메인 참고 |
| 확장 생성셋 | 1,938 | 형식 변형 견고성 | micro F1 0.825 | 안정성 보조 근거 |
| 합성 회귀 | seed별 60 | 코드 회귀 차단 | 다축 CI floor | 제품 정확도 근거 아님 |

정확한 scorer, 라벨 매핑, gold 제약과 비교 조건은 [`BENCHMARK.md`](BENCHMARK.md)를
따른다. 서로 다른 표의 F1을 직접 합치거나 평균하지 않는다.

### 폐기된 근거

과거 “AI Hub 행정문서 + PII 자기 주입 200건, micro F1 0.901, PERSON F1 0.795”는
현행 운영 근거로 사용하지 않는다. 검출기와 가까운 규칙으로 PII를 주입한 방법이라 과적합과
gold 현실성 위험이 있고, 현행 540건 평가셋으로 교체됐다.

이전 수치는 이력 보존 목적의 [`EVALUATION_REPORT.md`](EVALUATION_REPORT.md)에만 남긴다.
제안서, README, 고객 승인, SLA 또는 “운영 가능” 판단에 인용하지 않는다.

## 도메인에 따라 결과가 달라지는 이유

### 구조적 식별자

다음 라벨은 형식, 길이, prefix, checksum 또는 명시 anchor가 강하다.

- RRN, FRN, CARD, BUSINESS_REG, CORP_REG
- PHONE, EMAIL, ACCOUNT, PASSPORT, DRIVER_LICENSE
- 명시 필드의 DOC_ID, PETITION_ID, PRESCRIPTION_ID

이 라벨도 실제 데이터의 공백·OCR·마스킹·허구 번호 분포가 달라질 수 있으므로 고객
qualification을 생략하지 않는다. 합성 데이터의 checksum-invalid 값은 실제 검출기 recall을
왜곡할 수 있다.

### 문맥형·준식별자

PERSON, ADDRESS, DT_BIRTH, POSITION, EDUCATION, MAJOR, AGE, HEIGHT, WEIGHT는
주변 문맥과 라벨 정책에 민감하다.

- 대화체는 1~2자 이름·별명과 생략된 문맥이 많다.
- 공문서는 `성명:`, 직책, 결재선, 주소 필드처럼 anchor가 많다.
- 의료·의약 문서는 체중·연령·날짜가 임상 수치인지 개인정보인지 구분해야 한다.
- 뉴스는 외국인명·기관·지명이 많아 공공 서식 사전과 분포가 다르다.

따라서 전체 micro F1만으로 critical leakage와 일반명사 과탐을 동시에 판단하지 않는다.

## Intended Use

| 사용처 | 기본 판단 | 필수 보완 |
|---|---|---|
| 공공·업무 문서 인제스트 | 우선 대상 | 고객 양식과 critical label qualification |
| RAG 검색 후 LLM 전달 | 사용 가능 후보 | 인제스트와 검색 양단 canary, 원문 로그 금지 |
| 로그·감사 데이터 | 구조적 PII에 적합 | 서비스별 ID 형식과 보존 정책 |
| 금융·보험 문서 | 조건부 | 계좌·카드·고객번호 실제 형식 검증 |
| 의약·의료 문서 | 조건부 | 신체속성·날짜 제외 정책, 민감정보 별도 검토 |
| 자유 대화·SNS | 단독 사용 비권장 | 문맥형 NER 또는 검증된 보조 모델 |
| 신문·일반 NER | 제품 범위 밖 | 일반 개체명 인식기 사용 |
| 법적 익명성 확정 | 제품 범위 밖 | 별도 법률·재식별 위험 평가 |

## 고객별 운영 자격검증

### 1. 범위 고정

- 처리 목적, 데이터 출처, 이용자와 downstream을 기록한다.
- 필요한 라벨과 제외할 라벨을 정한다.
- `tokenize`, `partial`, `redact` 중 전략과 Vault 복원 필요 여부를 정한다.
- 미탐과 오탐의 업무 영향을 라벨별로 구분한다.

### 2. 데이터 구성

- 실제 고객 문서에서 기간·문서유형·채널별 표본을 구성한다.
- critical identifier와 benign look-alike를 의도적으로 포함한다.
- 같은 템플릿의 복제본은 독립 표본으로 세지 않는다.
- 개발에 사용한 예제와 qualification set의 중복을 검사한다.

### 3. 지표

| 구간 | 필수 보고 |
|---|---|
| Critical identifiers | 라벨별 TP/FP/FN, recall, precision, checksum-valid/invalid 분리 |
| Contextual labels | PERSON·ADDRESS 등 라벨별 confusion count와 문서유형별 편차 |
| Document safety | critical PII가 하나라도 남은 문서 비율 |
| Transformation | 원문 누출, 토큰 안정성, Vault 복원·권한·감사 |
| Operations | latency, 오류, degraded, parser별 실패, raw 로그 여부 |

critical identifier는 qualification set의 관측 미탐 0건을 요구한다. 이는 실제 미탐률이
0%라는 증명이 아니므로 표본 수와 신뢰구간을 함께 보존한다.

### 4. 운영 단계

1. Audit/shadow로 판정과 가명화 예상 결과만 관찰한다.
2. critical identifier부터 enforce하고 문맥형 라벨은 review 정책으로 시작한다.
3. 문서유형별 block·review·누출 지표가 사전 기준을 통과하면 범위를 확대한다.
4. 사전과 정책을 변경하면 같은 frozen qualification set과 신규 drift set을 모두 재실행한다.
5. 데이터 출처, 파서, OCR, 문서 템플릿 또는 downstream이 바뀌면 재승격한다.

## 운영 판단

현재 공개 증거로 허용되는 표현:

- “한국어 구조적 PII를 결정론적으로 검출·가명화하는 software-stable 라이브러리”
- “명시한 공개 데이터셋과 채점 조건에서 측정한 결과”
- “고객별 도메인 qualification을 전제로 한 배포 후보”

허용되지 않는 표현:

- “모든 한국어 개인정보를 탐지”
- “법적 익명화 또는 개인정보보호법 준수 보장”
- “공개 벤치마크만으로 운영 검증 완료”
- “데이터셋과 조건을 생략한 정확도 1위”

고객 환경에서 실제 qualification, shadow, canary와 운영 owner의 잔여위험 결정을 기록한
후에만 Tenant-qualified로 승격한다.
