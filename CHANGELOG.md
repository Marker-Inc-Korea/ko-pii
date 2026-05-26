# Changelog

본 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)
형식 + [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

## [Unreleased]

## [1.1.0] - 2026-05-21

Phase 9 (실데이터 평가 + 룰 정제) 완료. KDPII 53,778 문서 실데이터
벤치마크 도입. PERSON 풀네임 (3자+) 만 평가 기준 (개인정보보호법 제2조).

### Added — 평가 인프라

- `eval/kdpii.py` — KDPII 평가 모듈 (`--person-min-length=3` 기본)
- `eval/fp_collector.py` — 자동 과탐 어휘 수집 도구
  (비식별 텍스트 → PERSON 과탐 → common_words 후보 추출)
- 합성 코퍼스 8 → **13 템플릿** 확장:
  - press_release / audit_report / contract / hr_appointment / admin_disposition

### Added — 사전 확장

- `dictionaries/districts.py`:
  - 동 사전 +85개 (COMMON_DONGS)
  - 국가명 사전 70+ (COUNTRIES)
  - 시 약칭 60+ (EXTRA_CITY_ABBREV)
- `dictionaries/universities.py`: 약칭 +30 (3자 정식형 누락 보강)
- `dictionaries/titles.py`: 권사/집사/매니저/학생회장/길드장 등 30+
- `dictionaries/majors.py`: 학과 +70 (실용음악과/예술학과 등)
- `dictionaries/common_words.py`: KDPII 자동 수집 어휘 ~200 + 공문서 어휘 ~30
- `patterns/person.py`: `_COMMON_KOREAN_ENDINGS` 한국어 어말 16종 사전

### Added — 검출 정확도

- AGE: 한글 음역 일의자리 단독 ("한 살/세 살"), 환갑/팔순 등 명사,
  N개월 영유아 anchor, "30대" 연령대 패턴
- ADDRESS: 국적 접미사 자동 strip ("한국인" → "한국")
- DT_BIRTH: 30+ 비-생일 키워드 거부 ("선고일자/시행일자/배포일자" 등)
- PHONE: 대표번호 (15xx-18xx) 8자리 패턴 추가
- EDUCATION: 정규식 outer named-group 분리 (X대/X고/X중/X초 약칭 매칭)

### Added — IO + 메타데이터

- `io_/docx.py`: DOCX 메타데이터 (creator/lastModifiedBy/title) 추출
- `io_/hwpx.py`: HWPX 메타데이터 추출

### Changed — 평가 정책 (Breaking)

- KDPII 평가 기본값: PERSON 풀네임만 (3자+) — 개인정보보호법 제2조
  정의상 단독 1-2자 별명은 PII 아님. `--person-min-length=1` 으로 이전
  동작 복원 가능.
- KLUE-NER 평가도 풀네임만 (이전 2자+ → 3자+)
- 합성 코퍼스 위치 명확화 — "회귀 감지 sanity check" 으로 격하 (실제
  정확도는 KDPII / 공공 문서 본문 산문 측정)

### Documentation

- `docs/EVALUATION_REPORT.md` — 통합 평가 보고서 (한국어 명명 정탐/오탐/미탐)
- `docs/kdpii_evaluation_report.md` — KDPII 결과 보고서
- `docs/domain_fit_report.md` — 도메인 적합도 분석
- `docs/kdpii_visual_compare.html` — KDPII 100 문서 시각 비교

### 정확도 (KDPII 53,778 문서, PERSON 풀네임만)

| Tier | 카테고리 | F1 |
|---|---|---:|
| S | EMAIL/VEHICLE/FRN/RRN/IP/PHONE/URL | 0.99+ |
| A | WEIGHT/HEIGHT/DRIVER_LICENSE/ACCOUNT/AGE | 0.82~0.92 |
| B | PASSPORT/MAJOR/DT_BIRTH/EDUCATION/POSITION | 0.55~0.80 |
| C | ADDRESS | 0.52 |
| D | PERSON/CARD | 0.14~0.19 |
| **전체** | | **0.699** |

- 공공 문서 본문 산문 (메인 도메인): F1 ≈ 0.83
- 합성 13 템플릿: F1 = 0.85 (회귀 감지 sanity)
- KLUE-NER PERSON 풀네임: F1 = 0.376

## [1.0.0] - 2026-05-15

첫 정식 릴리스. 한국 공공 부문 PII 검출·가명화 도구로 production-ready 수준
도달. 외부 ML 없이 룰만으로 합성 공문서 F1=1.000, KLUE-NER (한국 인명만)
F1=0.331 달성.

### Added — Phase 11: OpenAI Privacy Filter 어댑터 (옵셔널 ML 통합)
- `integrations/` 모듈 — SecondaryDetector 프로토콜 + 어댑터들
- OpenAI Privacy Filter 어댑터 (Apache-2.0, 1.5B params, 다국어 PII)
- Hybrid Anonymizer — 4가지 병합 모드 (union/intersection/cross_validation/enrich_primary)
- `[ml]` extras — `transformers>=4.40`, `torch>=2.0` (옵셔널)

### Added — Phase 10: 솔루션 인프라
- HWP 5.x (OLE) + PDF 입력 — `[file]` extras (`olefile`, `pypdf`)
- 표 컬럼-단위 처리 (`tabular.py`) — CSV/XLSX 헤더 자동 매핑 (80+ 헤더)
- Vault 암호화 (AES-256-GCM + PBKDF2 480k iter) — `[security]` extras
- 감사 로그 (JSONL, 모든 reveal 추적) — 보호법 제29조 직접 대응
- 배치/병렬 처리 (multiprocessing) — CLI `--batch --workers N`
- 검토 큐 + 피드백 학습 (`review/`) — 사람-시스템 협업
- HTML 검토 리포트 (단일 정적 파일)
- 한자 → 한글 변환 + Revised Romanization

### Added — Phase 9: 부분 마스킹 + FPE + 식의약·법조 도메인
- `modes/partial.py` — 부분 마스킹 (홍OO, 880101-1******, 010-****-5678)
- `modes/fpe.py` — 형식 보존 가명화 (RRN 체크섬 자동 재계산)
- 신규 PII: KCD (질병코드), EDI_DRUG, COURT_CASE (법원 사건번호)

### Added — Phase 8: 결합 위험도 + k-익명성
- `analytics/combined_risk.py` — 식별자/준식별자/민감속성 4분류 + 조합 평가
- `analytics/k_anonymity.py` — k-익명성 평가 + 일반화 제안
- 신규 PII: PNU (필지고유번호)

### Added — Phase 7: 평가 + 문서화
- 합성 공문서 생성기 (6 템플릿, Faker 불사용)
- Precision/Recall/F1 메트릭 + 벤치마크 CLI
- KLUE-NER 외부 평가 (한국어 자연어 NER) + Korean-only 모드
- `docs/` — legal_mapping, risk_levels, coverage, real_data_evaluation

### Added — Phase 6: 통합 API + 정책 + 리포팅 + CLI
- `Anonymizer` 통합 클래스
- `ProcessingMode` (PARANOID/STRICT/BALANCED/PERMISSIVE/AUDIT)
- `legal/mapping.py` — 카테고리 ↔ 법조항 단일 매핑
- `reporting/{summary,certificate}.py` — 감사 증명서
- `ko-pii` CLI 엔트리포인트

### Added — Phase 5: Vault + 처리 모드
- `vault/reversible.py` — 가역 가명화 (JSON schema v1, salted SHA-256)
- 6 처리 전략: tokenize / redact / asterisk / hashed / partial / fpe
- `generalization/` — 연령·날짜·주소·직업 일반화

### Added — Phase 4: 도메인 특화 룰
- `domain/government.py` — DOC_ID
- `domain/civil_petition.py` — PETITION_ID
- `domain/hr.py` — EMPLOYEE_ID

### Added — Phase 3: 컨텍스트 기반 이름 탐지
- 한국 성씨 사전 (286개)
- 직책 사전 (일반직 + 경찰 11계급, 소방 11계급, 군 19계급, 검사·법관·외무)
- 부처·청·위원회 사전 (정부조직법 19부6처18청6위원회 + 약칭)
- 행정구역 사전 (17 광역 + 226 기초자치단체)
- 한국어 조사 처리 + 누적 사전 (NameDictionary)
- 컨텍스트 점수 시스템 + 점수 보강 룰 (음절 통계, co-occurrence 등)

### Added — Phase 2: 비검증 PII (정규식 + 컨텍스트)
- PHONE (국제 +82 포함), EMAIL, POSTAL_CODE, IP (v4+v6),
  VEHICLE, URL, ADDRESS (도로명+지번), ACCOUNT, FAX

### Added — Phase 1: 결정적 PII (체크섬)
- RRN (주민등록번호) + 후-2020 무작위화 대응
- FRN (외국인등록번호)
- BUSINESS_REG, CORP_REG (체크섬)
- DRIVER_LICENSE, PASSPORT
- CARD (Luhn)
- MEDICAL_INSURANCE

[Unreleased]: https://github.com/modak000/ko-pii/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/modak000/ko-pii/releases/tag/v1.0.0
