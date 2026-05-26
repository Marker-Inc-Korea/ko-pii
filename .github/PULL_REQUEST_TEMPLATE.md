<!-- 작성 가이드: CONTRIBUTING.md 의 컨벤션을 따릅니다. -->

## 변경 요약

<!-- 한 문장으로 무엇이 바뀌었는지 -->

## 변경 유형

- [ ] 버그 수정
- [ ] 새 PII 카테고리 (법적 근거 + 위험도 + 테스트 포함)
- [ ] 사전 데이터 확장 (출처 명시)
- [ ] 새 입력 포맷 / 통합 어댑터
- [ ] 검출 룰 정밀화
- [ ] 문서 / CI / 기타

## 체크리스트

- [ ] `pytest -q` 통과
- [ ] 합성 코퍼스 회귀 없음 (필요 시 `python -m ko_pii.eval.benchmark`)
- [ ] 새 카테고리: `LEGAL_BASIS` + `RiskLevel` + 테스트 10+ 포함
- [ ] 새 의존성: extras 로 분리 (코어 deps 0개 원칙 유지)
- [ ] `CHANGELOG.md` `[Unreleased]` 에 항목 추가
- [ ] 문서 업데이트 (docstring + 필요 시 `docs/`)

## 관련 이슈

<!-- closes #123 / refs #456 -->
