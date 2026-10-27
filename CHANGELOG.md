# Changelog

본 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)
형식 + [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

## [Unreleased]

## [1.22.5] - 2026-10-27

### Fixed

- `fpe` PHONE/FAX/CARD는 숫자와 지원 구분자로만 구성된 제한 길이의 값만 변환합니다.
  명시적 표/JSON 필드나 저수준 변환에서 번호 뒤의 이름·이메일·주석이 그대로 남던
  문제를 수정했습니다. 미지원 입력은 원문 길이의 별표로 마스킹합니다.
- `partial` DT_BIRTH의 연도 보존을 2/4자리 연도와 `년생`으로만 구성된 값으로
  제한했습니다. `년생`으로 끝나는 복합 필드 전체가 보존되던 문제를 수정했습니다.
- `partial` PERSON의 성만 남은 짧은 값과 PASSPORT의 숫자 1~2자리 값은 전체를
  마스킹합니다. 가릴 중간 부분이 없어 원문 전체가 반환되던 문제를 막습니다.

### Validation And Scope

- 표, JSON Pointer, FieldRule, PolicyProfile, 단일 값, 저수준 span 변환을 같은
  재현 사례로 검사하고 정상 번호 형식과 기존 부분 보존 정책도 회귀 검사합니다.
- Windows/macOS CI에도 새 검사를 포함합니다. 기본 탐지 규칙·의존성·임계값과
  AUDIT 동작은 바꾸지 않았으며 외부 데이터셋의 정확도 향상을 주장하지 않습니다.
- 필드 단언이 전략의 정보 보존 정책을 해제하지 않는다는 점과 FPE Vault에 원문이
  저장된다는 점을 구조화 입력 가이드에 명시했습니다.

## [1.22.4] - 2026-10-27

### Fixed

- `partial`/`fpe` EMAIL 변환은 지원하는 단일 주소일 때만 도메인을 보존합니다.
  표/JSON의 명시적 필드나 저수준 변환에 주소 목록/부가 문장이 들어오면 전체 마스킹하여
  첫 번째 주소 뒤의 다른 이메일이 원문으로 남던 문제를 막습니다.
- bounded/isolated 문서 읽기는 XML 파서에서 DTD를 거부합니다. UTF-16 LE/BE 선언이
  ASCII 바이트 검사를 통과하던 문제를 수정하고 기존 구성요소별 추출 실패 보고는 유지합니다.
- `enrich_primary`는 원본 primary마다 secondary 보강을 한 번만 적용합니다.
  같은 후보의 중복 반환으로 신뢰도와 실제 변환 여부가 달라지지 않습니다.
- k-익명성은 선택한 열이 모든 행에 있는지 확인합니다. 준식별자가 없으면 통과가 아닌
  미평가(k=0, satisfies_threshold=False)를 반환하고 잘못된 threshold/열 설정을 거부합니다.
- 저수준 `partial` span 평가는 최대 일대일 매칭으로 예측/gold 순서에 따른 점수 변화를
  없앴습니다. 미지원 mode를 거부하며 strict 평가와 별도 KDPII 매처의 조건은 유지합니다.
- `FileReadPolicy`는 정수 제한과 유한 압축률을 검사해 NaN으로 제한이 꺼지는 설정을
  거부합니다. 명시적 `column_map`에서 실제 행에 없는 열도 변환 전에 거부합니다.

### Migration And Validation

- 복합 EMAIL의 개별 부분 마스킹이 필요하면 먼저 필드를 분리하세요. 공통 column_map은
  현재 표의 실제 열로 범위를 정해야 합니다. 희소 행의 키 합집합과 빈 매핑은 지원합니다.
- 과거 partial 점수와 비교하려면 같은 매처로 양쪽을 다시 측정하세요. 과거 벤치마크 수치를
  재측정했다고 주장하지 않습니다. k-익명성의 미평가를 통과로 사용하지 마세요.
- 인코딩별 DTD/정상 문서, 변환 진입점별 복합 필드, 중복 후보, 설정 오타, 평가 순열과
  작은 그래프의 완전 탐색 대조 검사를 추가했습니다. 코어 의존성과 기본 탐지 규칙은 그대로입니다.

## [1.22.3] - 2026-10-26

### Fixed

- XLSX `read_records()`가 평문을 다시 split하지 않고 XML 셀 구조와 시트별 헤더를
  직접 읽습니다. 셀 내부 탭/줄바꿈을 보존하고, 서로 다른 시트의 열 순서 때문에
  이메일이 비매핑 열로 이동하던 문제를 수정했습니다.
- CSV/XLSX의 중복 또는 빈 헤더와 XLSX의 헤더 밖 비어 있지 않은 셀은 명시적으로
  거부합니다. XLSX의 끝쪽 빈 서식 셀은 무시하고, CSV의 기존 overflow restkey는
  보존합니다. 값이 조용히 덮어써지거나 잘리는 성공 결과를 방지합니다.
- `cross_validation`은 실제 primary만 확인 근거로 사용하고 primary마다 한 번만
  신뢰도를 보강합니다. secondary 중복/입력 순서로 REVIEW/BLOCK/ALLOW가 바뀌던
  문제를 수정했으며, 단독 후보의 기존 0.7 감점은 유지합니다.
- 정책상 비차단 후보가 밀린 경우 trace에 `non_blocking_policy_priority`를 기록합니다.
  하이브리드 설명에는 `block_risk_confidence_length_start`를 표시하며, 보조 탐지기 없는
  기존 설명 계약은 유지합니다.

### Documentation And Validation

- Presidio recognizer 직접 호출과 AnalyzerEngine 통합을 구분하고, 명시적 `ko`
  engine/registry를 사용하는 모델 다운로드 없는 실행 예제와 실제 SDK CI를 추가했습니다.
- 표 경계, 교차검증 중복/순서, 실제 선택 이유에 대한 회귀 검사를 추가했습니다.
  MCP는 별도 stdio 프로세스와 초기화/목록/가명화/복원 왕복도 검사합니다.
- 표 처리 오류의 거부 범위와 하이브리드 로그 변경을 안내했습니다. 새로운 ML/OCR
  기능이나 전체 탐지 정확도 향상을 주장하는 릴리스는 아닙니다.

## [1.22.2] - 2026-10-26

### Fixed

- Anonymizer 병합에서 현재 정책의 BLOCK 후보가 낮은 신뢰도 ALLOW/REVIEW 후보에
  밀리지 않도록 했습니다. 같은 차단 여부 안에서는 기존 위험도·신뢰도·길이 순서를 유지합니다.
- LlamaIndex는 검색 노드를 복사한 뒤 처리하며, LangChain은 Document ID를 보존합니다.
  본문과 metadata의 JSON 문자열 값을 같은 Vault로 처리합니다. 미지원 입력/metadata
  객체와 마스킹이 필요한 metadata 키는 조용히 통과시키지 않고 거부합니다.
- `fallback_secondary`는 REVIEW primary를 완전히 덮는 같은 라벨의 더 높은 신뢰도
  결과를 사용하도록 구현했습니다. 부분 일치나 secondary 단독 후보는 채택하지 않습니다.
- 배치 출력이 PERSON 제외 설정과 충돌하면 쓰기를 시작하기 전에 실패합니다.
  빈 스트리밍 청크는 버퍼 목록에 누적하지 않습니다.
- MCP 2.x의 호환되지 않는 서버 API가 설치되던 문제를 막기 위해 extra를
  `mcp>=1.0,<2`로 제한하고, 지원하지 않는 SDK에는 설치 안내를 반환합니다.

### Documentation And Validation

- MCP 도구 호출은 전송 전 필터가 아니며 detect/reveal이 원문을 반환함을 명시했습니다.
  원문이 LLM 또는 공급자 학습에 노출되지 않는다는 잘못된 설명을 제거했습니다.
- `cross_validation`은 기존의 신뢰도 감점 후 정책 적용을 유지합니다. 단독 후보가
  무조건 REVIEW라는 설명을 정정하고 STRICT 0.7 임계값 경계 테스트를 추가했습니다.
- 소스 배포본만 있는 임시 디렉터리에서 제품 테스트와 설치 예제를 검증합니다.
  연구 데이터 테스트는 `--run-research`로 분리하며 Git checkout CI에서는 계속 필수입니다.
- 실제 RAG 라이브러리와 MCP 1.x SDK의 합성 호출 계약 및 실패 경계를 CI에 추가했습니다.
  외부 모델, 실제 개인정보, 고객 문서는 사용하지 않습니다.

### Migration

- RAG metadata는 bounded JSON 값만 받으며 숫자/ID/질의/템플릿까지 자동 보호하지 않습니다.
  LangChain dict 입력은 먼저 처리할 필드를 선택해야 합니다. 상세 범위는
  [RAG 안내](docs/RAG_BOUNDARIES.md)를 참고하세요.
- 이 릴리스는 알려진 출력·연동 오류 수정이며 기본 규칙의 정확도 개선이나 법적
  익명성 보장이 아닙니다. 과거 외부 평가와 데이터 권리 미확정 사항도 해소됐다고 주장하지 않습니다.

## [1.22.1] - 2026-10-26

### Maintenance

- 한국어/영어 README를 시작 안내와 기능별 문서 링크로 맞추고, CONTRIBUTING의 오래된
  테스트 개수 및 F1=1.000 요구를 실제 CI 기준으로 수정했습니다. 과거 소개는 1.22.0
  태그에 보존하며 현재 지원 범위와 역사적 평가를 구분합니다.
- 태그 배포가 공통 검증 워크플로를 반드시 통과하도록 변경했습니다. sdist에서 만든
  wheel을 설치해 테스트하고 README Python·텍스트 CLI·JSON CLI 예제를 실행합니다.
  게시 job은 같은 실행의 파일을 해시·버전·소스 커밋으로 확인하고 재빌드 없이 게시합니다.
- 실제 PyPI 1.22.0으로 만든 합성 호환 fixture를 추가했습니다. 공개 export/호출 형태,
  기존 Vault 복원·다음 토큰, 정책 fingerprint, 설명 좌표와 CLI 출력을 검사합니다.
  공개 API·CLI·JSON·Vault 계약과 최신 1.x 보안 수정 정책을 문서화했습니다.
- 과거 연구 자료의 출처·권리 확인 상태·해시·구문 상태를 목록화했습니다.
  손상된 생성기 하나는 추측 복원하지 않고 실행 불가로 명시했습니다.
- 고정 리비전·파일 해시·사전 고정 표본 선정법을 쓰는 외부 합성 평가 runner를 추가했습니다.
  기본 CI는 외부 데이터를 받지 않으며 이번 정비에서 탐지 규칙·정책 기본값은 바꾸지 않습니다.
  K-PII-Bench 500건의 대응 라벨 strict-span F1 0.5513, 미완전 치환 939/1,877 span을
  숨기지 않고 라벨별·도메인별로 기록했습니다. 1.22.0과 1.22.1의 측정 집계는 동일하며
  공식 upstream 점수나 고객 환경 성능 보증이 아닙니다.

## [1.22.0] - 2026-10-26

### Fixed

- `CallableDetector`를 통하지 않고 직접 연결한 `secondary_detector`도 원문 좌표와
  값의 일치, 라벨, 위험도, 유한 신뢰도 및 메타데이터 타입을 검증합니다. 잘못된 결과나
  탐지기 예외는 해당 문자열의 치환/Vault 저장 전에 값 없는 `ValueError`로 반환합니다.
  정상 결과의 메타데이터는 유지하고, 재사용되는 결과 객체는 yield 시점에 복사합니다.
- `merge_mode`와 `role_split_labels` 오타를 Anonymizer 생성 및 저수준 병합 시 거부합니다.
  잘못된 위임 라벨로 탐지 결과가 조용히 제외되던 경로를 막습니다. `None`의 기본 위임
  라벨과 명시적 빈 목록의 의미는 유지합니다.

### Added

- `LiteralDetector`로 호출자가 이미 아는 값을 기존 라벨에 연결합니다. 정규식 문자를
  이스케이프하고 `word`/`substring`/`korean` 경계를 선택합니다. Korean 모드는 한글 PERSON의
  제한된 조사 접미사를 허용하며 원문 좌표를 보존합니다. 사전/입력/결과 크기를 제한하고
  대소문자·유니코드 정규화나 알려지지 않은 개인정보 탐지는 수행하지 않습니다.
- 불변 `PolicyProfile`과 CLI `--policy`로 코어·필드 설정을 재사용합니다. Python 처리와
  텍스트/JSON 미리보기가 같은 설정 검증을 사용합니다. 프로필은 버전, 설정 해시와 JSON
  내보내기를 제공하며 CLI 정책 옵션과의 혼용, 잘못된 설정, 설정 파일 덮어쓰기를 거부합니다.
- 평가 입력의 선택적 `metadata.domain`/`metadata.variant`로 조건별 TP/FP/FN, 라벨별
  지표와 실제 출력 잔존을 집계합니다. 정답이 없는 그룹의 recall은 null입니다.
  조건 배정도 데이터셋 해시에 포함하며 탐지 실행을 반복하지 않습니다.
- 평가 CLI의 `--provenance`로 정확한 입력 파일 SHA-256과 선언된 revision/split을 묶습니다.
  해시 불일치와 다른 출처의 baseline 비교는 거부합니다. 리비전의 외부 진위는 검증하지 않으며
  평가셋/모델 다운로드나 외부 벤치마크 점수 향상을 주장하지 않습니다.
- `compare_json_policies()`와 `ko-pii-compare-policies --format json`으로 필드 단언,
  배열 규칙, 필드별 PERSON 제외 설정을 변경 전후로 비교합니다. 기존 텍스트 API와
  보고서 계약은 유지하고 JSON에는 별도 `ko-pii-structured-policy-preview-v1`을 사용합니다.
  원문/치환값/키 경로는 기본 출력하지 않으며 경로만 `--include-paths`로 선택할 수 있습니다.
  처리하지 않은 정수 필드는 `before_screened`/`after_screened`로 구분합니다.

### Migration

- 직접 연결한 탐지기는 올바른 `DetectionResult`를 반환해야 합니다. 정규화한 문자열의
  좌표가 아니라 전달받은 원문의 Python 문자 좌표와 일치하는 값을 반환하세요.
  `RiskLevel` enum과 0~1 신뢰도를 사용하며 잘못된 결과를 자동 보정하지 않습니다.
- 이 검증은 임의 코드 실행 샌드박스나 전체 JSON/JSONL의 Vault 롤백이 아닙니다.
  직접 연결한 탐지기에 래퍼의 입력/결과 개수 제한이 자동 적용되는 것도 아닙니다.
- JSON 미리보기는 단일 JSON 값 대상이며 JSONL은 지원하지 않습니다. 100,000자,
  10,000노드, 문자열/정수 1,000필드, 관측 위치 2,000개로 제한합니다.
  두 정책 모두 놓친 개인정보나 전체 문서의 안전성을 평가하지 않습니다.

## [1.21.0] - 2026-10-22

### Added

- JSON/JSONL의 `field_person_exclusions`와 CLI `--field-person-exclusions`로
  정확한 필드에만 PERSON 제외어를 적용합니다. 기존 전역 제외어와 합산하며 다른 라벨,
  형제 필드, 다음 호출에는 영향을 주지 않고 명시적 필드 라벨 단언을 우회하지 않습니다.
- `RegexDetector` / `CallableDetector`를 기존 `secondary_detector`에 연결할 수 있습니다.
  기존 라벨, 원문 좌표/일치, 위험도, 유한 신뢰도 및 입력/결과 수를 검증합니다.
  사용자 정의 코드는 신뢰된 애플리케이션 코드로 한정하며 실행 샌드박스를 제공하지 않습니다.
- 이메일 ASCII/한글 도메인/난독화 경로의 안정적인 `subrule_id`와 선택적 겹침 추적을
  추가합니다. `Anonymizer(trace_limit=...)`, `explain(..., include_trace=True)`, CLI
  `--trace-limit`로 사용하며 원문 없이 제외 사유와 한 개의 겹친 후보, 잘림 여부를 기록합니다.
  탐지기 내부 탈락, 병합 정책의 제외, 모든 미탐을 설명하는 기능은 아닙니다.
- Hypothesis는 개발 의존성으로만 추가합니다. Unicode 원문/출력 좌표, 이메일 문장 경계,
  Vault 왕복, 겹침 알고리즘과 필드 격리의 생성형 불변조건 테스트를 CI에서 실행합니다.

## [1.20.1] - 2026-10-22

### Fixed

- 난독화 이메일이 앞의 영문 문장이나 이전 줄의 헤더까지 포함해 치환하던 오류를
  수정합니다. `[at]`/`[dot]` 및 구분자 주변 space/tab은 계속 인식합니다.
- 숫자 우회 방지용 정규화에서 제거되는 제어문자 줄 구분자를 이메일 경로에서는
  보존합니다. 숫자 식별자의 제어문자 삽입 탐지와 원문 좌표는 유지합니다.
- Vault 로드 시 토큰/라벨/양의 번호, 원문 타입, 위험도/위치, 역방향 매핑,
  fingerprint 설정을 검증합니다. 손상된 매핑이 새 토큰을 기존의 다른 원문에
  연결하지 않도록 하며, store에서도 매핑 충돌을 상태 변경 전에 거절합니다.
- Vault JSON의 중복 키와 비유한 숫자를 거부합니다. 정상적인 기존 schema v1 파일과
  legacy fingerprint 방식은 유지하고, 실패한 로드는 원본 파일을 변경하지 않습니다.
- 기본/명시적 이메일 처리, 정상/손상 Vault, 암호화 로드 및 생성 roundtrip 사례를
  회귀 테스트에 추가합니다. 새 런타임 의존성은 없습니다.

### Migration

- 이메일 로컬 파트 내부의 단어를 자동으로 합치지 않습니다. 기본값에서
  `hong gildong @ naver . com`은 `gildong @ naver . com`만 탐지합니다.
  분리된 이메일 필드에서만 저수준 `email.detect(..., allow_spaced_local=True)`로
  내부 space/tab 복원을 선택할 수 있습니다. 두 모드 모두 줄을 넘겨 복원하지 않습니다.
  이는 산문 과잉 치환을 줄이는 대신 모호한 공백/줄바꿈 난독화의 탐지 범위를 좁히는 변경입니다.
- 잘못된 Vault는 자동 수정하지 않고 `ValueError`로 거절합니다. 명시적
  fingerprint_iterations는 양의 정수여야 합니다. 자세한 내용은
  [이메일·Vault 업데이트 안내](docs/EMAIL_AND_VAULT_MIGRATION.md)를 참고하세요.

## [1.20.0] - 2026-10-22

### Added

- `FieldRule`/`EACH`와 `--field-rules`로 반복 배열, 선택 필드 및 누락/빈 배열/null 집계를
  지원합니다. 선택 필드여도 타입 오류는 거부하며, JSONL 전체를 선검증합니다.
- `compare_policies()`와 `ko-pii-compare-policies`로 코어 정책 변경의 관측 라벨/위치별
  영향을 비교합니다. 별도 메모리 Vault만 사용하고 원문/치환값은 보고하지 않습니다.
  두 설정 모두 놓친 개인정보나 전체 문서의 정확도/익명성을 평가하지 않습니다.
- 신청서·대화·자유 서술 합성 회귀 사례와 휴대전화 접두어/표기 조합 검사를 추가합니다.
  평가 보고서에 실행 환경의 로컬 `evaluation_date`를 기록합니다.
- `Anonymizer(strategies={...})`로 한 번의 탐지/치환에서 라벨별 전략을 적용합니다.
  기존 `strategy`는 기본 전략이며 처리 모드의 BLOCK/REVIEW/ALLOW 기준은 유지합니다.
- `anonymize_json()` / `anonymize_jsonl()`로 중첩 문자열 값을 처리합니다. 정확한 JSON
  Pointer에 대한 `field_labels`는 필드 전체의 라벨 단언으로 동작합니다. 일반 숫자,
  불리언, null과 키는 보존하고, 명시적으로 변환한 정수 식별자만 문자열이 됩니다.
- JSON 입력의 중복 키, 순환 객체, 비JSON 타입, 비유한 수, 잘못된 Unicode,
  과도한 중첩/길이와 잘못된 필드 매핑을 오류로 처리합니다. JSONL은 전체 입력을
  검증한 뒤 처리하며, Vault/외부 감사 시스템까지의 트랜잭션은 보장하지 않습니다.
- 값 없는 버전 지정 `reporting.explain()`과 구조화 결과의 `report()`를 추가합니다.
  선택된 탐지기 계열, 원문/출력 좌표, 정규화, 제한된 검사 코드, 실제 적용 전략을
  기록합니다. 원문, 토큰, 자유 형식 evidence/extra, 경로는 기본 보고서에 넣지 않습니다.
- CLI `--format json|jsonl`, `--strategy-for`, `--field-label`, `--explain`을 추가합니다.
- 로컬 K-PII-Bench JSONL을 기존 평가기로 연결하는 어댑터를 추가합니다. 지원 밖 라벨은
  별도 집계하고, surface와 offset 불일치는 거부합니다. 외부 데이터는 자동 다운로드하지 않습니다.
- `ko-pii-evaluate --fail-on-new-retained`와 `--output-strategy-for`로 혼합 정책 및 실제
  출력 잔존의 회귀를 검사합니다. 정책이 다른 두 결과를 코드 회귀처럼 비교하지 않습니다.

### Fixed

- FP/FN 판정을 철회하면 관리 대상 피드백 파일도 다시 생성하여 오래된 후보를 제거합니다.
- 검토 큐의 손상/스키마 오류/중복 ID를 조용히 버리지 않습니다. 원본을 유지하고 실패하며,
  mark 저장 실패 시 메모리도 유지합니다. 동시 작성자 잠금/자동 복구는 추가하지 않습니다.
- 문서에 명시됐지만 패턴에서 빠져 있던 `018` 휴대전화 접두어를 국내/국제/괄호 표기에 추가합니다.
- 탐지 0건을 개인정보 부재로 읽을 수 있는 문구를 관측 범위 기준 설명으로 바꿉니다.
  기존 위험도 임계값은 유지하고 include/exclude/빈 입력/필드 단언 범위를 요약에 남깁니다.
- `user@예시.kr` 등 한글 도메인 라벨과 ASCII 최종 라벨이 있는 이메일을 탐지합니다.
  Unicode local-part/Unicode 최상위 도메인 전체 지원을 의미하지 않습니다.
- JSONL 레코드를 LF로 구분하여 문자열 내부의 Unicode 줄 구분자가 레코드를 나누지
  않도록 합니다. 원문 기준 탐지/치환 위치를 계속 유지합니다.

### Security and Migration

- 처리 증명서는 기본적으로 검토 원문, 치환값, 문서 식별자를 포함하지 않습니다.
  검토 항목의 개수와 위치는 계속 표시합니다. `include_review_details=True`,
  `include_replacements=True`, `include_document_id=True`는 민감한 내부 검토용입니다.
  CLI의 `--report-include-sensitive`도 동일한 명시적 선택이며 외부 공유용이 아닙니다.
- 원문과 Vault를 포함하는 메모리 객체 및 원문 표시용 HTML 보고서는 여전히 민감합니다.
  새 보고 형식은 법적 익명성이나 탐지 누락의 부재를 인증하지 않습니다.
- JSON 키는 처리하지 않습니다. JSON Pointer도 키를 포함하므로 `report(include_paths=True)`는
  민감 정보를 노출할 수 있습니다. 정확한 필드 매핑이 문서에 없으면 오류가 발생합니다.
- 번호가 영문 제품 코드 안에 포함된 사례는 정상 연락처 누락을 피하기 위해 기존의
  보수적 탐지를 유지합니다. 전역 ASCII 경계 필터로 일괄 제외하지 않습니다.
- 기존 경쟁 도구 비교를 과거 구성의 기록으로 명시하고, 현재 Presidio의 한국 식별자
  지원과 최신 모델/과거 체크포인트 차이를 반영합니다. 새 비교 수치로 가장하지 않습니다.

## [1.19.1] - 2026-10-22

### Fixed

- 전각/NFKC 정규화 이후 숫자 닮은꼴 폴딩과 자릿수 공백 처리를 적용하여,
  `０１０-１２Ｏ４-５６７８` 같은 복합 표기의 탐지 누락을 수정했습니다.
  원문 좌표를 합성하고 영문 식별자 전체 경계 검사는 유지합니다.
- FPE가 `[at]` 이메일 등 지원하지 않는 형식을 원문 그대로 반환하던 경로를
  전체 별표 마스킹으로 대체했습니다. 정규화만으로 값이 달라진 것을 가명화로
  간주하지 않으며, 변환 결과가 원래 값과 같은 경우에도 전체 마스킹합니다.
- FPE 전화/카드의 유니코드 숫자 판정을 통일해 위첨자 숫자 등에서 발생하던
  `IndexError`를 수정했습니다. 변환 전 숫자 정규화를 적용하고, 지원하지 않는
  비ASCII 문자는 기본 문자 매핑에서 그대로 보존하지 않습니다.
- Anonymizer, 단독 `fpe()`, `anonymize_value()`, 표 API가 같은 안전 처리 경로를
  사용합니다. Vault에는 정규화본이 아닌 원문과 실제 출력의 대응을 저장합니다.
- 부분 마스킹의 숫자 정규화를 통일하고, CARD/ACCOUNT로 직접 지정된 8자리 이하
  값이 앞뒤 보존으로 전부 노출되는 경계 사례를 전체 마스킹합니다.

### Documentation

- FPE를 암호화로 소개하던 표현을 형식 보존 결정적 가명값 매핑으로 바로잡았습니다.
  FF1/FF3가 아니며 Vault 보관과 키 관리는 별도라는 점을 명시합니다.
- 비표준 입력의 정규화와 안전 대체 처리에서는 길이·구분자·이전 출력이 달라질 수
  있습니다. 일반 지원 형식의 매핑·지문 설정과 부분 마스킹의 의도된 정보 보존은 유지합니다.

## [1.19.0] - 2026-10-22

### Fixed

- ASCII 숫자 닮은꼴 문자(`010-12O4-5678`)의 정규화가 주변에 한글이 있는지에 따라
  달라지던 문제를 수정했습니다. 영문 식별자 내부의 부분 문자열은 폴딩하지 않고,
  검출 위치와 텍스트는 원문 기준으로 유지합니다.
- 구분자 없는 `880` 시작 번호를 바코드로 제외할 때, 바로 앞에 명시된 주민번호
  필드를 고려합니다. 체크섬 불일치는 기존의 낮은 확신도로 남으며, 날짜·성별 자리
  검사는 유지합니다. 문서 다른 곳의 주민번호 언급은 예외 근거가 아닙니다.
- 표 처리의 `AUDIT` 모드가 매핑된 셀을 변형하고 Vault에 저장하던 문제를 수정했습니다.
  자동 매핑·직접 매핑·초과 셀 모두 원문과 기존 Vault를 보존합니다.
- 다수 탐지 시 겹침 검사와 치환 기록 연결의 반복 전체 탐색을 제거했습니다.
  겹침 선택은 기존 우선순위를 유지하는 O(n log n) 인덱스를 사용합니다.
  이메일 난독화 패턴도 유효한 at/domain 후보에서 시작하도록 바꿔 긴 비이메일
  숫자·단어 나열을 반복 탐색하지 않습니다. 코어 의존성은 추가하지 않았습니다.

### Changed

- 표 헤더 자동 추론의 기본값을 보수적으로 변경했습니다. `상품이름`, `filename`,
  `product_name`을 PERSON으로 강제 처리하지 않습니다. `신청인 연락처`는 PHONE으로
  인식하며, 알려진 대상 접두어와 완전한 필드명의 조합만 지원합니다.

### Migration

- `map_columns()`와 `anonymize_records()`의 `header_policy="legacy"`로 기존 첫 부분
  문자열 매칭을 복원할 수 있습니다. 기존 오탐도 함께 복원되므로 가급적 `column_map`
  으로 실제 열을 지정하십시오. 미매핑 열은 그대로 남으며 전체 표의 무PII 보장이 아닙니다.
- `AUDIT` 이외 모드에서 매핑된 열 전체를 강제 처리하는 기존 동작은 유지합니다.
  표 API는 탐지 보고서를 반환하지 않습니다. 값별 판정이 필요하면 `Anonymizer`를 사용합니다.
- SQL용 `classify_schema_columns()`는 기존대로 완전 일치·공백/대소문자 정규화만
  사용하고 복합 헤더 추론은 하지 않습니다.

## [1.18.0] - 2026-10-21

### Fixed

- 알 수 없는 include/exclude 라벨과 빈 include를 처리 전에 거부합니다. 오타를
  검출 0건으로 표시하며 원문을 내보내던 경로를 차단했습니다.
- `anonymize_value()`와 빈 레코드 처리에서 전달한 빈 Vault를 유지하므로 기존
  salt, 매핑 수명 주기, 감사 실패 정책이 새 객체로 교체되지 않습니다.
- DOCX/HWPX/XLSX의 손상된 텍스트 구성요소를 조용히 생략하지 않고 문서 실패로
  반환합니다. XLSX의 잘못된 공유 문자열 참조도 빈 셀로 통과시키지 않습니다.
- 배치 출력의 해시 접미사가 기존 출력 이름과 다시 충돌하는 경우에도 고유 경로를
  배정합니다. 명시한 누락 입력을 실패 목록에 포함하고 generator 라벨 필터를 한 번만 소비합니다.
- CLI의 Vault·감사·저장 관련 예상 가능한 오류를 종료 코드와 구조화된 오류로 반환합니다.
  실패 응답에는 처리 단계, Vault 저장 여부, 결과 출력 상태를 포함합니다.

### Added

- `ko-pii-evaluate --output-mode STRICT --output-strategy redact --fail-on-retained`로
  정답 위치와 실제 출력 치환 기록을 대조합니다. 탐지 실패, 정책상 유지, 부분 치환,
  의도된 일부 마스킹과 치환 후 원문 잔존을 구분합니다. 익명성 인증은 아닙니다.
- `AnonymizationResult.substitutions`에 실제 적용한 원문/출력 좌표를 제공합니다.
- DOCX/HWPX/XLSX `inspect_text()`의 부분 검토 결과와 제한된 추출/CLI/배치의
  `extraction_coverage` 또는 `coverage` 보고를 추가했습니다. 이미지·미지원 구성요소는
  검사 완료로 주장하지 않습니다.
- 배치의 건너뛴 경로·실패 사유 보고와 명시적 빈 작업 허용 옵션 `--allow-empty`를 추가했습니다.
- Windows/macOS의 설치 CLI·worker·Vault·병렬 배치 테스트와 선택적 RAG 연동 CI를 추가했습니다.

### Migration

- 라벨은 `ko-pii --labels`에 나온 정확한 대문자 키를 사용합니다. Python API에서
  `include=None`은 전체 검사, `include=[]`는 오류, `exclude=[]`는 제외 없음입니다.
- CLI `main()`을 Python에서 직접 호출할 때 운영 오류는 예외 대신 종료 코드 1을
  반환합니다. 잘못된 라벨 설정은 2입니다. 인자 구문 오류는 기존 argparse 동작을 유지합니다.
- 부분 문서는 기본 처리 경로로 통과시키지 않습니다. `inspect_text()`는 명시적 검토용이며
  OS 샌드박스나 전체 포맷/OCR 완전성 보장은 아닙니다.

## [1.17.0] - 2026-10-21

### Added

- 사용자 JSONL 정답 문서의 라벨별 TP/FP/FN을 측정하고 이전 보고서와 새 미탐·오탐을
  비교하는 `ko-pii-evaluate`를 추가했습니다. 원문 없는 JSON 보고서와 회귀 종료 코드를
  제공하며, 데이터셋·라벨·매칭 조건이 다르면 비교를 거부합니다.
- `read_text_isolated()`와 CLI·배치의 파일별 추출 프로세스에 크기·압축 해제량·문자 수와
  timeout을 적용했습니다. Linux worker에는 512 MiB 주소 공간 제한도 적용합니다.
- PDF `inspect_text()`에 페이지 수·추출 실패·텍스트 없는 페이지 정보를 추가했습니다.
- `detect_all()`, `Anonymizer`, 배치와 CLI에 설치 패키지의 전역 사전을 수정하지 않는
  프로젝트별 `person_exclusions` / `--person-exclusions-file`을 추가했습니다.
- `ReversibleVault`에 감사 기록 실패를 전파하는 `audit_failure_policy="raise"`를
  추가했습니다. CLI에서 `--audit-log` 사용 시 기본값은 실패 폐쇄입니다.

### Changed

- **파일 처리 변경:** PDF 페이지 오류와 텍스트 없는 페이지를 더 이상 빈 문자열로 조용히
  통과시키지 않습니다. OCR 또는 수동 검토가 필요한 문서는 실패로 반환합니다.
- CLI·배치가 기본적으로 제한된 추출을 사용하므로 큰 문서는 명시적으로 한도를 조정해야
  합니다. [파일 처리·이전 가이드](docs/FILE_PROCESSING.md)를 참조하십시오.
- 평문·암호화 Vault와 결과·리포트는 임시 파일의 flush/fsync 후 교체하며 POSIX에서는
  새 파일을 0600 권한으로 만듭니다. 여러 파일의 트랜잭션이나 동시 writer 잠금은 아닙니다.
- 평문 Vault 저장 시 원본 개인정보 포함 경고를 출력하고, Vault의 인증·인가·키 관리와
  감사 로그 무결성이 애플리케이션 책임임을 보안 계약 문서에 명시했습니다.
- OOD·속도·소표본 도메인 점검 수치가 독립 검증이나 운영 보장으로 읽히지 않도록 평가
  조건과 qualification 문구를 구체화했습니다.

### Fixed

- CLI가 Vault 저장 실패 전에 가명화 결과를 출력하던 순서를 바로잡았습니다. 암호화 Vault의
  읽기·쓰기에서 비밀번호는 한 번만 입력받고 빈 대화형 암호는 거부합니다.
- 입력·출력·Vault·리포트·감사 파일 경로 충돌을 거부하고 재실행 시 배치 결과 폴더를
  다시 수집하지 않습니다. 배치의 미지원 ML·단일 파일 출력 옵션도 명시적으로 거부합니다.
- 선택적 PDF 의존성이 설치되지 않은 코어 전용 환경에서도 PDF fallback 단위 테스트가
  테스트 더블을 주입할 수 있도록 수정했습니다.
- CLI 배치 모드에서 Vault·감사 옵션이 조용히 무시되던 동작을 명시적 오류로 바꾸고,
  `best_effort` 감사 로그 열기 실패와 JSON 요약의 경고 혼입을 처리했습니다.
- 감사 로그 종료를 결과 출력보다 먼저 수행하고, CLI 익명화 이벤트를 출력 저장 완료가 아닌
  `status="prepared"`로 구분했습니다. JSON 요약과 대화형 비밀번호 프롬프트 조합도 거부합니다.
- PERSON 제외 목록을 사용하지 않는 기본 탐지 경로에서 불필요한 후보별 Unicode 정규화를
  건너뛰고, Unicode 원문 경계 복구 패스가 제외된 이름 조각을 다시 검출하지 않도록 수정했습니다.

## [1.16.0] - 2026-09-02

### Added

- SQL 정책 컴파일용 `classify_schema_columns()`를 추가했습니다. 기존 표 처리의 부분 문자열
  추론과 달리 정확·정규화 일치만 허용하고 모호한 헤더에는 신뢰도 근거를 반환합니다.
- schema lineage가 확정된 단일 값을 검출기 추론 없이 처리하는 `anonymize_value()`를
  추가했습니다.
- 신뢰하지 않는 문서의 파일·ZIP 멤버·압축 해제량·압축률·XML DTD·엔티티·추출 문자 수를
  제한하고 콘텐츠 없는 provenance를 반환하는 `read_text_bounded()`를 추가했습니다.
- 전송 조각 사이에 나뉜 식별자를 놓치지 않도록 원문을 먼저 내보내지 않고 bounded buffer에서
  완성한 뒤 한 번에 가명화하는 `PreForwardAnonymizer`를 추가했습니다.

### Fixed

- 최신 `pdfplumber`와 `pypdf`의 타입 정보를 함께 사용할 때 선택적 PDF 추출 백엔드의
  페이지 타입이 충돌하던 정적 검사 오류를 수정했습니다.

### Documentation

- 소프트웨어 안정성과 고객 도메인 qualification을 분리한 제품 계약을 추가했습니다.
- 폐기된 자기 주입 벤치마크의 “운영 가능” 주장을 제거하고, 공개 측정값을 분포별 참고
  근거로 제한하는 도메인 승격 기준으로 교체했습니다.
- 데이터셋과 조건을 생략한 “정확도 1위” 표현을 제거했습니다.

### Maintenance

- CI와 릴리스 워크플로의 JavaScript 액션을 Node.js 24 기반 버전의 전체 커밋 SHA로
  갱신했습니다.

## [1.15.4] - 2026-07-28

### Added
- 합성 회귀 gate를 micro precision/recall/F1과 macro-F1 독립 하한으로 확장하고,
  실패한 지표의 실측값과 기준값을 CI 로그에 출력.

## [1.15.3] - 2026-07-28

### Added
- Python 3.10/3.12/3.14, 정적 분석, 배포물 격리 설치와 합성 회귀를 독립 CI
  필수 gate로 추가.
- `ko-pii-benchmark --min-micro-f1`로 명시한 회귀 하한 미달 시 비정상 종료.

### Fixed
- 합성 벤치마크가 점수와 관계없이 항상 성공하던 CI 계약을 실제 종료 코드로 수정.

## [1.15.2] - 2026-06-18

### Fixed
- 전화번호 검출 오류 수정

## [1.15.1] - 2026-06-11

### Fixed
- **`ko-pii --version` 표기 오류** — `__version__` 이 1.13.0 에 고정돼 있던 것을 수정
  (1.13.1~1.15.0 은 pyproject 만 갱신됨). pyproject 와의 동기화 테스트 추가 (드리프트 가드).

## [1.15.0] - 2026-06-11

### Added
- **`ko-pii --labels`** — 33종 PII 카테고리(include/exclude 라벨 키)를 그룹·한글명·
  검출방식과 함께 CLI 에서 조회. `input` 없이 단독 실행 가능.
- **`ko_pii.labels` 모듈** — `ALL_LABELS`/`LABEL_INFO` 정본 레지스트리.
  redact 한글 치환명과 테스트로 동기화 보증 (드리프트 가드).

### Docs
- README 한/영 33 카테고리 절에 CLI/코드 조회 안내 추가.

## [1.14.0] - 2026-06-10

### Added
- **`MergeMode.ROLE_SPLIT`** — 토큰 NER 하이브리드(룰=결정적 ID, ML=퍼지 *교체*)를
  라이브러리 병합 모드로 제공. `Anonymizer(secondary_detector=..., merge_mode="role_split",
  role_split_labels=...)`. 프로젝트 구축 OOD Set A에서 **F1 0.968** 로 측정
  — `docs/HYBRID_NER.md` 분포 외 보조 평가 절.
- **`HFTokenNERAdapter`** (`ko_pii.integrations.hf_token_ner`) — HYBRID_NER 레시피로
  직접 학습한 토큰분류 NER 을 `secondary_detector` 로 꽂는 범용 어댑터 (lazy 로드,
  BIO 디코딩은 torch 없이 테스트 가능한 순수 함수).
- `[classifier]` extra 에 `datasets` 추가 — `python -m ko_pii.classifier.train` 이
  extra 설치만으로 동작하도록.

### Fixed
- **RRN 공백 구분자 변형 검출** — 서식 표기 `880101 - 1234568`(공백+하이픈+공백)이
  구분자 2자 제한에 걸려 미검출되던 갭 수정(하이브리드 NER 체크섬 프로브에서 발견).
  공백으로 감싼 구분자만 추가 허용 — 순수 공백 3자(표 칼럼 나열)는 계속 비허용으로
  FP 확대 없음. 회귀 테스트 3건 추가.
- `PIIClassifier.from_pretrained` — 모델 경로가 없을 때 raw HuggingFace 에러 대신
  "가중치 미배포 — 직접 학습" 안내가 담긴 `FileNotFoundError`.

### Docs
- README 예제 실측 교정(한/영) — `combined_risk` 속성명(`distinct_identifiers`/
  `distinct_quasi`), `k_anonymity` 시그니처(`quasi_keys`/`threshold`/`satisfies_threshold`),
  `anonymize_records` 튜플 반환 언패킹, partial 표기(`홍OO`), IntEnum 출력(`.name`).
  전 스니펫 실행 검증 완료.
- README 하이브리드 절 — **두 하이브리드(토큰 NER vs 문서 분류기) 구분 표** +
  `role_split` 사용법 추가 (오독 방지).
- `experiments/ner` 이식성 — 스크립트 8종 절대경로 제거(레포 상대 + env 폴백),
  `code/requirements.txt`(실측 스택 고정) 신설. 외부 머신 재현 검증 완료.

## [1.13.1] - 2026-06-10

### Fixed
- **[보안 HIGH] 병합경로 PII 평문 누출 차단** — `integrations/hybrid._resolve_overlaps` 가
  start-우선 단일커서 방식이라, 늦게 시작하는 고위험 PII(주민번호·전화)가 먼저 시작한
  저위험 span 에 가려 평문으로 남던 회귀 수정. 겹침 해소를 `core/overlap.resolve_overlaps`
  정본 1곳으로 통일 (detect / `modes._apply` / hybrid 공유) + end-to-end 누출 회귀 테스트.

### Added
- **train↔test 문장 누수 가드** — `ko_pii.eval.dataset_integrity.assert_no_text_leakage`
  (빌드타임 누수 검증) + 단위 테스트.

### Docs
- 하이브리드 NER ablation 실측 반영 (`docs/HYBRID_NER.md`) — klue 3ep 포화,
  openai/privacy-filter "구조적 부적합" 판정을 under-training 으로 정정, 재현 레시피 절 추가.
- README 한/영 동기화 (튜닝 NER 공개 예정 멘트 + HYBRID_NER 포인터).
- OpenMed/PF-multilingual 후속 평가 문구 정리 (평가 계획 없음으로 확정).

## [1.13.0] - 2026-06-09

### Fixed
- **건강보험증번호 형식 확장** — 증번호 표기형 `N-NNNNNNNNNN`(종별코드 + 하이픈 + 10자리)
  검출 추가. 기존엔 순수 11자리만 인식. 키워드 anchor 유지로 FP 안전.
- **처방번호 형식 확장** — EMR 영문 접두 형식(`RX-2026-008471`, `PRSC-2026-...` 등)
  검출 추가. 기존엔 `YYYYMMDDNNNN` 12자리만 인식. 키워드 anchor 필수.
- 합성 평가셋(540) 기준 MEDICAL_INSURANCE 0.0 → **0.893**, PRESCRIPTION_ID 0.0 → **0.718**,
  전체 ko-pii F1 0.784 → **0.790**.

### Added
- **회귀 게이트 테스트** — `tests/unit/eval/test_generated_eval_regression.py`. 커밋된
  합성 평가셋으로 ko-pii 전체/라벨별 F1 하한을 CI(`pytest`)에서 자동 검증.
- **확장 평가셋** — `data/generated_eval_large.jsonl` (1,938문서 = 540 검증분 + LLM 생성
  1,398). 독립 시스템 견고성 대조에서 ko-pii **0.825** (3.6× 큰 셋에서도 우위 유지).

## [1.12.1] - 2026-06-05

### Docs (문서만, 코드 변경 없음)
- **KDPII 비교 공정성 각주** — 전체 점수는 해외 도구가 *라벨 자체가 없는* 카테고리
  (AGE·POSITION·RRN 등)에서 0점이라 격차가 부풀려진다. 각 도구가 **실제 지원하는
  카테고리만**으로 좁혀도 ko-pii 우위(vs openai/privacy-filter 0.61:0.37, vs
  Presidio 0.87:0.65)임을 README·README.en·BENCHMARK 에 명시.
- **보충 벤치마크 교체** — 행정문서 PII 주입(ko-pii 자기 주입 데이터, 과적합 우려)
  대신 **LLM 생성 벤치마크**(187문서, 1,199 spans, 32개 PII 카테고리 *완전 커버*,
  ko-pii 룰 미참조 독립 데이터, F1 0.770)를 보충 수치로 사용 — 더 정직한 측정.

## [1.12.0] - 2026-06-04

심층 적대적 누출 스윕(27 에이전트, 발견별 실행 재현 검증)에서 확인된 **PII 평문
누출 10건 + 데이터 손실 + ReDoS** 수정. 각 수정은 전체 테스트 + repro 재현으로
검증, 회귀 테스트 22개 추가. 핵심 발견: **정규화 계층("우회 차단" 기능)이 일부
입력에서 오히려 누출을 *만들고* 있었다.**

### Security (PII 평문 누출 차단)
- **보이지 않는 문자가 인접 PII 를 융합** — 제로폭 공백(U+200B)·소프트하이픈·BOM
  등 제거가 `RRN​전화` 처럼 붙은 두 PII 의 경계를 지워 양쪽 검출기 가드가 둘 다
  거부 → 평문 누출. 정규화본 + 원본 **dual-pass 검출 합집합**으로 해소.
- **U+2A74(⩴) NFKC→'::='** — PII 숫자열에 `::` 가 주입돼 검출을 쪼개고 가짜 IPv6
  매치를 유발. 제거 대상에 추가.
- **제어문자·결합표시가 PII 를 쪼갬** — C0 제어문자(탭·개행 제외)·DEL·C1·숫자
  결합표시(U+0301 등)가 PII 숫자열 한가운데 끼면 미검출. `needs_normalization`
  가드로 ASCII 제어문자도 정규화 경로를 타게 하고, 숫자 베이스 결합표시 제거.
- **구분자 변형으로 유효 PII 미검출** — 점(.) 구분 주민등록번호, `+82` 국제표기
  유선전화, 점/슬래시 구분 카드번호가 검출 안 돼 평문 통과. 패턴 확장(체크섬·Luhn
  이 오탐 차단).
- **셀 줄바꿈 래핑(`-\n`)으로 분리된 PII** — 표 셀 래핑·복붙 줄바꿈으로 쪼개진
  RRN/전화/카드 미검출. 구분자 슬롯 `{0,2}` 확장 + 모든 IO 포맷에
  `normalize_for_detection` 적용(이전엔 PDF 만).
- **표 처리 누출** — `anonymize_records` 가 `records[0]` 키만으로 컬럼을 추론해
  이질/희소 레코드의 PII 컬럼이 평문 통과 → 전체 키 합집합 추론. ragged CSV 의
  초과 셀(csv restkey 리스트)도 자동 검출 스캔.

### Fixed
- **배치 출력 경로 충돌 데이터 손실** — 서로 다른 디렉토리의 동명 파일이 같은
  `out/<stem>.txt` 로 충돌해 마지막 결과가 이전 결과를 덮어쓰던 문제. 충돌 시
  입력 경로 해시로 disambiguate.
- **ReDoS (주소 정규식)** — 도로명/지번 패턴의 중첩 `[가-힣]+` 가 긴 한글런에서
  super-quadratic 백트래킹(8,000자 수초). 길이 제한으로 선형화(~23ms).

### Known / Deferred
- 설계 결정이 필요한 3건은 별도 보류: `BALANCED` 모드가 MEDIUM 위험(유선전화·
  이메일)을 통과, `partial` 전략이 짧은 값을 과노출, `fpe` 형식보존이 일부 정보
  (도메인·성별자리·prefix)를 유지.

## [1.11.3] - 2026-06-02

### Fixed
- **`[all]` extra 에 `pdfplumber` 누락 수정** — `pip install ko-pii[all]` 시 `pdfplumber` 가 설치되지 않아 PDF 파싱이 degraded 되던 패키징 결함. `[file]` 과 일치하도록 `[all]` 에 추가.

### Changed (eval 내부 — 채점 정합)
- **KDPII 채점 단일 매처 통일** — 매칭 알고리즘이 `kdpii.py`(substring-set)와 `model_comparison.run_kdpii_three_way`(중복 인라인)에 따로 존재해 숫자가 갈리던 결함 수정. canonical `kdpii.match_forms_overlap`(public)로 일원화.
- **person_min_length 기본값 통일** — `evaluate_kdpii`(이전 1) / CLI / `run_kdpii_three_way` 모두 **3**(풀네임만; 한국어 PII 정의 부합)으로 일치.
- **3-way 에 Presidio 추가** — `run_kdpii_three_way(include_presidio=True)` / CLI `--include-presidio` → ko-pii·openai/PF·Presidio 를 *동일 매처*로 채점하는 재현 가능한 3-way 표. 회귀 테스트 추가(채점 정합 고정).

## [1.11.2] - 2026-06-02

### Security
- **지문(fingerprint) KDF 강화** — `hashed`/FPE 모드의 단일 SHA-256(salt 평문 저장)은 저엔트로피 PII(주민·전화)를 vault JSON 만으로 무차별 대입해 복원할 수 있었음. 개선:
  - **비밀 키(pepper)** 지원 — `ReversibleVault(secret_key=...)` 또는 env `KPII_FINGERPRINT_KEY`. **vault JSON 에 저장되지 않으므로**, 키 없이는 salt 를 알아도 원본 복원 불가.
  - **PBKDF2-HMAC-SHA256 stretching**(기본 100,000회) — 키가 없어도 대입 비용을 크게 높임. 고유 값당 1회만 계산(메모이즈)해 처리량 유지.
  - scheme 버전화(`pbkdf2-sha256-v2`) — 기존 vault(필드 없음)는 자동으로 legacy SHA-256 유지해 hashed/FPE 출력 일관성 보존.

## [1.11.1] - 2026-06-02

코드 점검 LOW 항목 중 실 영향 있는 것 + 무료 정확성/정리 반영.

### Fixed
- 가명화 모드(`modes/_apply`)의 겹침 해소가 `detect_all` 과 다른 키(시작위치 우선)를 써, 모드를 직접 쓸 때 낮은 우선순위 span 이 고신뢰 PII 를 가릴 수 있던 문제 → 동일 우선순위로 통일.
- `redact` 모드가 NATIONALITY 를 `[국적]` 대신 영문 라벨 `[NATIONALITY]` 로 치환하던 문제.
- FPE 전화 핸들러의 02 지역번호 dead branch — 02 번호의 가입자 1자리가 마스킹되지 않던 문제.
- PDF 칸 정규화(`_SPACED_FIELD`)가 띄어쓴 영문 단어("I a m f i n e"→"Iamfine")까지 붙이던 문제 → 숫자 칸만 정규화.
- classifier CLI 가 `[classifier]` 미설치 시 raw ImportError 대신 친절한 설치 안내 출력.

### Security
- `--vault-password` 에 값 없이 주면 프롬프트로 안전하게 입력(getpass), 값 직접 지정 시 노출 경고.

### Changed
- 죽은 코드 정리 — name_origin 의 매칭 불가 다글자 음절(뷔트·비스·위치·샹송), name_syllables 중복 엔트리(건·달), context_rules 미사용 import 제거.
- 문서 정정 — README 사업자등록번호 위험도 LOW→HIGH(코드와 일치), surnames 개수(~286→187), `io_` docstring(PDF/HWP `[file]` 지원 명시), `detect_all` docstring(겹침 우선순위 + 없는 CHANGELOG 참조 제거), README 테스트 수 표기.

## [1.11.0] - 2026-06-02

코드 전수 점검(8개 차원 다중 에이전트 리뷰 + 적대적 검증)에서 확인된 HIGH 5 + MEDIUM 11 수정. 각 수정은 전체 테스트 + 실데이터 재현으로 검증.

### Security
- **전화번호 평문 누출 차단** — 지번주소 패턴이 인접 전화번호의 앞자리를 삼켜 겹침해소 단계에서 진짜 PHONE 검출이 누락, 기본 `BALANCED` 모드에서 전화번호가 평문 통과하던 문제. 지번/도로명 번지 그룹에 `(?![0-9-])` 추가 + 겹침해소를 우선순위 기반으로 재작성.
- **URL 내부 PII 누출 차단** — `http://…?ssn=…&m=…@…` 처럼 URL(INFO) 이 내부 RRN/EMAIL 을 삼켜 마스킹되지 않던 문제. 겹침해소가 이제 더 높은 위험도·확신도 검출을 우선.
- **NFD(유니코드 분해형) 우회 차단** — 분해형 한글(예: "홍길동")이 정규화로 합성되지 않아 PERSON 검출을 회피하던 문제. 클러스터 단위 NFKC 합성 + offset 역매핑 보정.
- **감사로그 완전성** — 실패한(존재하지 않는 토큰 probing) `reveal()` 과 재 `store()` 호출이 기록되지 않던 문제. 이제 `found`/`new` 플래그와 함께 모두 기록.

### Fixed
- **법인등록번호 체크섬 알고리즘 정정** — 잘못된 Luhn식 자릿수 축약 → 공식 규격(가중치 곱을 직접 합산)으로 수정. 실 법인번호(예: 삼성전자 130111-0006246)를 정상 검증. 순환 참조였던 테스트 벡터도 외부 검증 가능한 실번호로 교체.
- **법인번호 RRN 오라벨 정정** (D-003) — 법인번호가 RRN 약한 폴백(0.7)으로 오라벨되던 문제. 성별자리=0 + 법인 체크섬 통과 시 CORP_REG 로 분류(실 RRN 은 그대로 보호).
- **ㄹ/ㄴ 두음 성씨 오분류** — 류현진·라미란·노무현 등이 'foreign' 으로 분류되던 문제. 성씨 판정을 외래어-두음 규칙보다 우선.
- **FPE 한글 형식 깨짐** — 기본 FPE 핸들러가 한글을 라틴 문자로 치환하던 문제(`str.isalpha()` 가 한글에 True). 한글 → 한글 치환으로 형식 보존.
- **XLSX 열 정렬** — 빈 셀이 생략되어 이후 열이 왼쪽으로 밀리던 문제. 셀 `r` 좌표 기반 배치.
- **CSV 멀티라인 셀** — 따옴표 안 줄바꿈에서 셀이 깨지던 문제(`io.StringIO` 사용).
- **HWP 제어문자** — inline/extended 제어문자의 14바이트 payload 가 텍스트로 새거나(코드 5~8 등) 데이터 없는 char control 을 과소비(24~26)하던 문제를 HWP 5.0 명세 기준으로 정정.
- **HWPX 문단 융합** — `linesegarray` 없는 문단이 분리자 없이 다음 문단과 붙던 문제(`<hp:p>` 경계에 줄바꿈).
- **kdpii eval recall 부풀림** — 1자 성씨 예측이 풀네임 gold 의 부분문자열로 TP 처리되던 문제(짧은 쪽 2자 이상일 때만 부분매칭).
- `__version__` 이 1.2.0 으로 정체돼 있던 문제 → 패키지 버전과 동기화.

### Changed
- `detect._resolve_overlaps` 가 시작 위치가 아니라 **위험도→확신도→길이** 우선순위로 겹침을 해소 (낮은 우선순위 span 이 고신뢰 PII 를 가리지 않도록).

## [1.10.0] - 2026-06-01

### Removed
- **건물명 가제티어 제거** (1.4.0~1.8.0의 `dictionaries.buildings`, `is_building_name`/`building_names`, `building_names.txt.gz`, `scripts/build_address_gazetteer.py`). 실효 검증 결과 실제 코퍼스(KDPII 5만 + 행정 gold)에서 발동 0회 — 자연스러운 주소는 동/호/층 bridge 또는 건물 접미사 룰이 이미 커버하기 때문. 11K 데이터·API 유지 가치 없음 → 제거
- **참고(BREAKING)**: `is_building_name`/`building_names` 직접 사용 시 영향. 주소 내 건물명 검출 자체는 **bridge(동/호/층 앞 토큰) + 접미사 38종 룰로 그대로 유지** (대부분 케이스 동일 동작)

## [1.9.0] - 2026-06-01

### Added
- **법정동 가제티어 (anchor 조건부)** — 전국 법정동(동/읍/면/리) **10,368건** (국토부 법정동코드, data.go.kr). 단독 행정구역 검출 분기에서 **강한 주거 anchor(살던/이사/거주 등)가 있을 때만** emit → 대화체 주소 커버리지 확대 (`is_legal_dong`, `legal_dongs`)
- 2글자·일반어 충돌(변동·수리·관리·거리 등) 제외, 길이 3+ 만 채택

### Notes
- **FP 측정**: KDPII 9,902 대화문장에서 법정동으로 추가된 ADDRESS 검출은 **+2건뿐, 둘 다 진짜 주소**("애월읍 살아서", "갈월동 내 집 주소") → anchor 게이트로 FP 0 확인

## [1.8.0] - 2026-06-01

### Added
- **건물명 가제티어 실데이터 탑재** — 시드 10건 → **11,124건**. K-apt 공동주택관리정보시스템 관리비공개의무단지 기본정보(2026.05.29, data.go.kr)의 전국 단지명에서, 접미사 룰이 못 잡는 비접미사 고유명만 증류(단일토큰·길이4+·일반어 제외). "수성하늘채르레브"처럼 브랜드가 끝이 아닌 단지명까지 ADDRESS 로 검출
- `scripts/build_address_gazetteer.py` — `.xlsx` 입력 + `--header-row`/`--source` 지원 (K-apt 재현 가능)

### Notes
- 가제티어 멤버십은 도로명+번호 주소 *직후* 토큰에만 적용 → 비주소 문맥에서 FP 없음 (검증)
- 법정동(10,635)·기관코드(157,303)도 검토했으나, 기관코드는 파출소·유치원·동사무소까지 초세분이라 PERSON/ADDRESS 오탐을 유발 → 미반영

### Added
- **룰+ML 하이브리드 분류기 (opt-in `[classifier]`)** — 문서 수준 ML 분류기로 룰 검출 보강:
  - `PIIClassifier` (transformers 시퀀스 분류) + `HybridAnonymizer` (SCORE/GATED/REVIEW_FLAG/UNION_BLOCK 4 모드) + `tfidf_baseline` (초경량 TF-IDF) + `ko-pii-classify` CLI
  - **코어는 ML 없이 그대로 동작** — `[classifier]` 설치 시에만 활성화, `import ko_pii` 는 torch 불필요
  - **모델 가중치는 미배포** (학습 데이터 라이선스: KLUE=CC-BY-SA-4.0 / KDPII=CC-BY-4.0 / AIHub=재배포 제한). 코드·학습 레시피(`ko_pii.classifier.train`)만 제공 → 본인 데이터로 학습
  - 분류기 테스트는 가중치/의존성 없으면 자동 skip (CI green 유지)

## [1.6.0] - 2026-05-31

### Added
- **RAG 파이프라인 연동** — 검색 결과를 LLM 에 넣기 전 PII 마스킹 (검색 → 마스킹 → LLM):
  - `KoPiiNodePostprocessor` (`integrations.llamaindex`) — LlamaIndex node postprocessor (`[llamaindex]`)
  - `KoPiiRedactor` (`integrations.langchain`) — LangChain `Runnable` (`[langchain]`)
  - 한 검색 결과 안에서 *같은 인물 = 같은 토큰*(`<PERSON_1>`) 일관성 유지 → LLM 이 동일 개체 추론 가능
  - `vault` 전달 시 답변 생성 후 `vault.reveal()` 로 권한 기반 복원
  - 모듈 import 는 프레임워크 없이도 안전 (soft import), 코어 의존성 불변
- README **"왜 필요한가"** 섹션 — PIPA·폐쇄망·결정적 검출 보완·RAG 양단 차단 프레이밍

## [1.5.0] - 2026-05-31

### Added
- **유니코드 정규화 (검출 우회 차단)** — `detect_all` 진입점에 **기본 적용** (`core.unicode_norm`):
  - 전각→반각 NFKC 폴딩: `０１０` → `010`, `①` → `1`, `㈜` → `(주)`
  - 제로폭/보이지 않는 문자 제거: 제로폭 공백(U+200B)·조이너·BOM·소프트하이픈·방향마크
  - 검출 offset 은 **원본 문자열 기준으로 역매핑** (redaction 정확성 보존), `.text` 원본 복원
  - ASCII 입력·정상 텍스트는 fast-path no-op (오버헤드 ~0), `normalize=False` 로 비활성화 가능
  - 외부 의존성 없음 (표준 `unicodedata`)

### Security
- 전각 숫자·제로폭 문자 삽입으로 RRN/전화/카드 검출을 우회하던 문제 차단

## [1.4.0] - 2026-05-31

### Added
- **주소 건물명 검출** — 도로명+번호 뒤 건물/단지명을 ADDRESS 에 포함. 사전 없이 위치로 식별:
  - 번호와 `숫자 동/호/층` 사이에 끼인 토큰 (양쪽 anchor)
  - 건물 접미사 38종 (빌딩·타워·센터·스퀘어·자이·래미안·푸르지오·힐스테이트·주공 등 실존 브랜드)
  - "월드컵북로 396 누리꿈스퀘어 12층" → 전체 단일 ADDRESS
- **건물명 가제티어** (`dictionaries.buildings`, `is_building_name`/`building_names`) — 접미사 없는 고유명("그랑서울" 등) 보완. 번들 gzip 리소스, **런타임 오프라인** 유지
- **`scripts/build_address_gazetteer.py`** — 행정안전부 도로명주소 DB(business.juso.go.kr, KOGL Type 1)를 증류해 가제티어 생성. 빌드타임 도구

## [1.3.0] - 2026-05-31

### Added
- **NATIONALITY 카테고리 신설** — 국가명/국적을 ADDRESS 에서 분리 (`patterns/nationality.py`, 70+ 국가 사전). "대한민국·미국·한국인" 등이 더 이상 주소로 오탐되지 않음 → 33 PII 카테고리
- RRN PDF 서식 prefix 검출 — 관계코드 등 1자리 숫자 접두 허용
- 사업자번호 칸별 공백+하이픈 혼합 패턴 정규화
- PDF 텍스트 정규화 + 전화번호 괄호 포맷 + 주소 공백 허용
- Gradio 실시간 비교 데모 (`demo/app.py`) + HF Spaces 배포

### Changed
- 주소 동호수+층 반복 확장 — "판교역로 235 103동 1502호" 전체를 단일 ADDRESS 로 검출
- README: openai/privacy-filter·Presidio 비교 수치 표, 파서 라이브러리 표, 조합 차단 FAQ 추가

## [1.2.0] - 2026-05-26

유지보수 릴리스. 1.1.0 이후 누적 정비 (상세는 git log 참조).

## [1.1.0] - 2026-05-21

Phase 9 — 실데이터 평가 + 룰 정제.

### Added
- KDPII 53,778 실데이터 평가 모듈 (`ko_pii.eval.kdpii`)
- 자동 과탐 어휘 수집 도구 (`ko_pii.eval.fp_collector`)
- 합성 코퍼스 6 → 13 템플릿 (회귀 감지용)
- 사전 확장: 행정구역 / 직책 / 학과 / common_words / 한국어 어말 16종
- DOCX·HWPX 메타데이터 추출

### Changed
- **[BREAKING]** PERSON 평가 기본값: 풀네임 (3자+) — 개인정보보호법 제2조.
  이전 동작은 `--person-min-length=1` 로 복원 가능.
- 검출 룰 정밀화: AGE / ADDRESS / DT_BIRTH / PHONE / EDUCATION

### 정확도
- 행정문서 본문 F1 ≈ **0.83** (메인 도메인)
- KDPII 53,778 문서 micro F1 = **0.699** (풀네임만)
- 상세: [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md)

## [1.0.0] - 2026-05-15

첫 정식 공개 릴리스. 한국 공공 부문 PII 검출·가명화 도구.

- 22 PII 카테고리 (RRN·FRN·여권·사업자·카드·계좌·전화·주소·인명·직책 등)
- 5 처리 모드 (PARANOID/STRICT/BALANCED/PERMISSIVE/AUDIT)
- 6 치환 전략 (tokenize/redact/asterisk/hashed/partial/fpe)
- Vault 가역 가명화 + 감사 로그 (JSONL)
- 결합 위험도 + k-익명성 평가
- HWP·HWPX·DOCX·PDF·CSV·XLSX 입력
- 외부 ML 통합 어댑터 (OpenAI Privacy Filter / Presidio, optional)
- `ko-pii` CLI + Python API

전체 Phase 1~11 개발 히스토리는 git log 및 `docs/` 참조.

[Unreleased]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.21.0...HEAD
[1.21.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.20.1...v1.21.0
[1.13.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.12.1...v1.13.0
[1.12.1]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.12.0...v1.12.1
[1.12.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.11.3...v1.12.0
[1.11.3]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.11.2...v1.11.3
[1.11.2]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.11.1...v1.11.2
[1.11.1]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.10.0...v1.11.0
[1.10.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.9.0...v1.10.0
[1.9.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Marker-Inc-Korea/ko-pii/releases/tag/v1.0.0
