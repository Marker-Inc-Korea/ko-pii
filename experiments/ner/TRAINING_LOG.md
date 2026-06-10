# 학습 레지스트리 — 실측 메타데이터

모든 수치는 실측(sacct Elapsed, HF Trainer `train_runtime`). 기계용 동일 데이터: [`runs.json`](runs.json).

## 공통 환경

- **GPU**: NVIDIA RTX PRO 6000 Blackwell 96GB × 1장/잡 (SLURM gres `rtx6000`, 노드 gpu01/gpu02)
- **스택**: Python 3.12 · torch 2.12.0(cu130) · transformers 5.10.2 · datasets 5.0.0 · seqeval 1.2.2
  (venv tarball staging — `code/*.sbatch` 참조)
- **데이터**: train 41,507 (KDPII 40,109 + 생성행정 1,398) / valid 5,011 / test = KDPII 4,891 + 생성 540
- **공통 하이퍼파라미터**: max_len 256 · warmup 0.1 · weight_decay 0.01 · valid F1 best 선택
  (변형은 표에 명시)

## 학습 런 (실행 순)

| 잡ID | 노드 | 베이스 (라벨) | lr·ep·bs | 순학습시간 | samples/s | KDPII | 생성540 |
|---|---|---|---|---|---|---|---|
| (직접) | head | klue/roberta-large (퍼지20) | 2e-5·3·32 | 796s (13.3분) | 156.4 | 0.934 | 0.846 |
| 3650 | gpu01 | klue/roberta-large (퍼지20) | 2e-5·3·32 | 867s (14.5분) | 143.6 | **0.937** | **0.862** |
| (직접) | head | openai/privacy-filter (퍼지20) | 2e-5·3·32 | 4,958s (82.6분) | 25.1 | 0.138 | 0.209 |
| 3653 | gpu02 | klue/roberta-large (퍼지20) | 2e-5·6·32 | 1,031s (17.2분) | 241.6 | 0.935 | 0.844 |
| 3654 | gpu01 | klue/roberta-large (퍼지20) | 3e-5·6·32 | 1,693s (28.2분) | 147.1 | 0.928 | 0.859 |
| 3655 | gpu01 | openai/privacy-filter (퍼지20) | 1e-4·5·32 | 6,619s (110분) | 31.4 | 0.633 | 0.437 |
| 3718 | gpu01 | klue/roberta-large (**전체36**) | 2e-5·3·32 | 1,407s (23.5분) | 88.5 | **0.950** | **0.882** |
| 3723 | gpu01 | gemma-4-E2B-it 텍스트타워 4.6B (**전체36**) | 5e-5·3·8×4 | 6,731s (112분) | 18.5 | 0.353 | 0.701 |
| 3744 | gpu02 | gemma-4-E2B-it 텍스트타워 4.6B (**전체36**) | 1e-4·3·8×4 | 4,336s (72분) | 28.7 | 0.351 | 0.673 |

- 동일 설정 반복(첫 두 행)의 차이 ±0.003~0.016 = 학습 무작위성.
- samples/s 차이는 노드 공유 상황(타 사용자 잡과 GPU 노드 공유)에 따른 변동 포함.
- gemma-4-E2B 는 transformers 에 토큰분류 클래스가 없어 커스텀 헤드
  (`code/gemma4_train_ner.py`) — bf16 풀 파인튜닝 + gradient checkpointing.
  두 lr(5e-5/1e-4) 모두 valid F1 ~0.33 에서 조기 정체 — 과소학습 아닌 구조적 천장.

## 평가 런

| 잡ID | 노드 | 내용 | 소요 |
|---|---|---|---|
| 3664 | gpu01 | 하이브리드 전후비교 v1 — openai/PF tuned | 6분52초 |
| 3665 | gpu02 | 하이브리드 전후비교 v1 — klue 퍼지 | 1분43초 |
| 3715 | gpu02 | 평가스위트 v2 — klue base(무학습) | 1분24초 |
| 3716 | gpu01 | 평가스위트 v2 — klue 퍼지학습 | 13분24초 |
| 3719 | gpu01 | 평가스위트 v2 — klue 전체학습 | 10분33초 |
| 3722 | gpu01 | 3안 (ML+룰 체크섬 검증) | 4분22초 |
| 3764 | gpu01 | 외부 검증 (Set A 6구성 + Set B 3구성) | 3분54초 |
| (로컬 CPU) | head | 체크섬 프로브 + 마스킹 시연 | 수 분 |

## 비용 요약

- klue(336M) 1회 학습 = **15~30분 / GPU 1장** — ablation 한 라운드(4종)가 반나절 안에 끝나는 규모.
- openai/PF(1.4B MoE) = klue 의 ~5배, gemma-4-E2B(4.6B) = klue 의 ~4~8배 학습시간.
- 전체 학습 GPU 시간 합계: 학습 ~7.9시간 + 평가 ~0.6시간.
