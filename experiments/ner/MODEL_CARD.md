# 모델카드 (초안 — 미공개)

> ⚠️ 본 문서는 **공개 결정 시 사용할 초안**입니다. 가중치는 아직 배포되지 않았습니다 —
> 공개 여부는 도메인 일반화 평가([`../../data/labeling/`](../../data/labeling/)) 결과 후 결정.

## ko-pii-ner-klue (가칭)

한국어 PII 토큰분류 NER — [ko-pii](https://github.com/Marker-Inc-Korea/ko-pii) 하이브리드의
퍼지 카테고리 담당 모델. `Anonymizer(secondary_detector=..., merge_mode="role_split")` 로 사용.

| | |
|---|---|
| 베이스 | klue/roberta-large (336M, 한국어 인코더) |
| 라벨 | 전체 36종 (퍼지 20 + 결정적 ID 16, BIO) |
| 학습 데이터 | KDPII train 40,109 + 자체 생성 행정문서 1,398 |
| 레시피 | lr 2e-5 · 3 epoch · max_len 256 · bs 32 (`code/train_ner.py`) |
| **라이선스** | **CC-BY-SA-4.0** (베이스 KLUE 의 SA 승계 — 레포 코드 MIT 와 별개) |

## 성능 (실측 — 출처: 본 디렉토리 results/)

| 평가 | 단독 | 하이브리드(role_split) |
|---|---|---|
| KDPII test (대화체, 인분포) | 0.950 | 0.904* |
| 생성 540 (행정체, 인분포) | 0.882 | 0.927* |
| **외부 OOD 주입 v2** (민원 도메인·체크섬 유효) | 0.929 | **0.968** |
| KLUE-NER PS (뉴스, 인간 라벨) | 0.840 | — |

\* 하이브리드 수치는 퍼지학습(20종) 변형 기준, 전체학습 모델은 0.898/0.924/0.966.

## 한계 (정직 고지)

1. **ID 검출은 패턴 매칭** — 체크섬 진위 검증 불가(실존 불가 번호도 검출). 결정성·검증이
   필요하면 하이브리드(ko-pii 룰이 ID 담당)로 사용할 것 — 이것이 권장 구성.
2. **인분포 편향** — ID 형식·행정체는 학습 분포와 유사할 때 최강. 실제 공공문서 인간 라벨
   검증은 진행 중(공개 게이트).
3. **경계 정확도** — 긴 숫자열에서 span 경계가 ±1자 어긋나는 사례 존재(겹침 기준 TP,
   정확 추출 기준 미흡 — 외부 검증 CORP_REG 사례).
4. **꼬리 케이스** — 별명·은어·1음절 성씨 약함 (KDPII NICKNAME 0.845, 그 외 보고서 참조).

## 출처표시 (attribution)

- 베이스: [KLUE](https://github.com/KLUE-benchmark/KLUE) (klue/roberta-large), CC-BY-SA-4.0
- 학습 데이터: [KDPII](https://zenodo.org/records/10968609) — Fei et al., IEEE Access 2024,
  DOI 10.1109/ACCESS.2024.3461804, CC-BY-4.0
- 생성 데이터: google/gemma-4-31B-it (Apache 2.0) 산출물

## 재현

가중치 없이도 동일 모델을 직접 학습 가능: [`README.md`](README.md) 재현 절 (GPU 1장 ~30분).
