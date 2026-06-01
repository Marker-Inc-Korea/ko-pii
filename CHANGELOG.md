# Changelog

본 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)
형식 + [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

## [Unreleased]

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

[Unreleased]: https://github.com/modak000/ko-pii/compare/v1.9.0...HEAD
[1.9.0]: https://github.com/modak000/ko-pii/compare/v1.8.0...v1.9.0
[1.8.0]: https://github.com/modak000/ko-pii/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/modak000/ko-pii/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/modak000/ko-pii/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/modak000/ko-pii/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/modak000/ko-pii/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/modak000/ko-pii/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/modak000/ko-pii/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/modak000/ko-pii/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/modak000/ko-pii/releases/tag/v1.0.0
