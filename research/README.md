# 연구 자료와 제품 검증의 경계

현재 제품은 `src/ko_pii`이며, 일반 사용에 이 디렉터리나 외부 평가 데이터를 받을 필요가 없습니다.

## 고정 외부 평가

[2026-10-26 측정 결과와 해석](EXTERNAL_EVALUATION_20261026.md)을 먼저 확인하세요.
기존 배포 1.22.0에서 micro F1 0.5513이 측정됐으며, 이 표본에 맞춘 룰 수정은 하지 않습니다.

[프로토콜](external-protocol.json)은 외부 작성자가 공개한 K-PII-Bench의 고정 리비전에서
500개 문서를 결과와 무관하게 SHA-256(doc_id) 순서로 선정합니다.
원본 파일 해시·크기·전체 문서 수도 확인합니다. 데이터는 CC-BY-4.0으로 공개된 합성 자료이며
upstream 저작자는 링크된 데이터 카드와 라이선스를 참고하세요.

현재 코어에 사용자 규칙이나 모델을 추가하지 않고 STRICT/redact로 실행합니다.
14개 대응 라벨의 엄격한 문자 span 점수, 라벨별·도메인별 결과, 실제 출력의 잔존 상태를
함께 기록합니다. 나머지 4개 upstream 라벨은 미지원으로 집계합니다.
KR_LOCATION과 ADDRESS의 의미 범위도 완전히 같지 않습니다.
upstream의 BIO 공식 점수나 실문서 검증으로 부르지 않습니다.

```bash
python scripts/evaluate_external.py --cache /tmp/ko-pii-external --output /tmp/ko-pii-external-report.json --download
```

최초 다운로드는 약 143 MB입니다. 그 뒤에는 `--download` 없이 동일 캐시를 사용할 수 있습니다.
기존 결과는 덮어쓰지 않습니다. 외부 코드를 실행하거나 모델을 받지 않으며 일반 CI에서는
다운로드하지 않습니다. 결과를 본 뒤 룰이나 표본 선정법을 맞추지 않는 정비 릴리스입니다.

## 역사적 자료

[catalog.json](catalog.json)은 Git에 추적된 `data/` 파일의 SHA-256·크기·출처·라이선스
확인 상태와 구문 검사 상태를 기록합니다. `python scripts/audit_research.py`로 확인합니다.
변경을 조용히 무시하지 않고 목록과 다르면 실패합니다.

- `legacy-parseable`: 구문 검사를 통과했을 뿐, 의존성·절대 경로·실험 결과까지 검증한 것은 아닙니다.
- `blocked`: 현재 실행할 수 없는 파일입니다. `data/build_eval_corpus.py`는 한국어 문자열과
  인용부호가 손상돼 있습니다. 원본을 추측 복원해 기존 gold라고 주장하지 않습니다.
- `historical-data`: 과거 입력·결과이며 최신 성능 주장의 근거가 아닙니다.

기존 경로와 파일은 보존했습니다. 과거 BENCHMARK/EVALUATION_REPORT/HYBRID_NER 및
발표 자료는 다른 데이터·라벨 정책·매처를 썼을 수 있어 현재 strict-span 점수와
직접 비교하면 안 됩니다. 옛 README는 v1.22.0 태그로 보존합니다.

## 데이터 권리

코드의 MIT 라이선스가 외부 데이터까지 포괄하지 않습니다.
KDPII는 [원 출처·CC-BY-4.0 고지](https://github.com/Marker-Inc-Korea/ko-pii/blob/main/data/kdpii/README.md)가 있으며,
KLUE와 AI Hub 파생 자료는 각각 원 배포처의 조건을 별도 확인해야 합니다.
특히 과거 AI Hub 파생 파일의 재배포 권한은 이번 인벤토리로 확정하지 못했습니다.
해당 파일을 새 데이터 제품으로 재배포하거나 사용 허가가 확인됐다고 표시하지 않습니다.
`data/` 전체는 wheel 및 sdist에 포함하지 않습니다.

자료를 새로 추가할 때 출처 URL, 리비전, 라이선스, 변경 사항과 해시를 함께 기록하세요.
실제 개인정보나 고객 문서는 공개 저장소에 넣지 마세요.
