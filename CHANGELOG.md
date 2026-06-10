# Changelog

본 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)
형식 + [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

## [Unreleased]

### Fixed
- **RRN 공백 구분자 변형 검출** — 서식 표기 `880101 - 1234568`(공백+하이픈+공백)이
  구분자 2자 제한에 걸려 미검출되던 갭 수정(하이브리드 NER 체크섬 프로브에서 발견).
  공백으로 감싼 구분자만 추가 허용 — 순수 공백 3자(표 칼럼 나열)는 계속 비허용으로
  FP 확대 없음. 회귀 테스트 3건 추가.

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
- **KDPII 에 Gemma-4-E4B 측정 추가** — 대화체 크기효과 문서화(작은 LLM은 ko-pii 미만).

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

[Unreleased]: https://github.com/Marker-Inc-Korea/ko-pii/compare/v1.13.0...HEAD
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
