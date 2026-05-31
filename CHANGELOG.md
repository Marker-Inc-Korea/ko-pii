# Changelog

본 프로젝트는 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)
형식 + [Semantic Versioning](https://semver.org/lang/ko/) 을 따른다.

## [Unreleased]

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

[Unreleased]: https://github.com/modak000/ko-pii/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/modak000/ko-pii/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/modak000/ko-pii/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/modak000/ko-pii/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/modak000/ko-pii/releases/tag/v1.0.0
