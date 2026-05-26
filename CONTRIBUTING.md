# Contributing to ko-pii

ko-pii 에 기여해주셔서 감사합니다. 본 가이드는 효율적인 협업을 위한
컨벤션·워크플로우를 정리합니다.

## 시작하기

### 개발 환경

```bash
git clone https://github.com/modak000/ko-pii
cd ko-pii
python -m venv .venv
source .venv/bin/activate    # Windows: .venv/Scripts/activate
pip install -e ".[dev,file,security]"
pytest    # 699 passed in ~2s 가 정상
```

옵셔널 (대용량 의존성):
```bash
pip install -e ".[ml]"    # OpenAI Privacy Filter 어댑터 (transformers + torch)
```

## 기여 유형

### 1. 사전 데이터 확장 (가장 큰 환영)

- `src/ko_pii/dictionaries/` — 성씨/직책/부처/행정구역/필드라벨/일반단어
- 새 도메인 어휘 (의료·금융·법조 등) PR 환영
- *출처를 명시* — 공개 데이터셋·정부 표준·통계청 자료 등

### 2. 새 PII 카테고리

`src/ko_pii/patterns/` 의 기존 모듈 (예: `rrn.py`) 을 레퍼런스로:

```python
"""<카테고리> (English Name) detection."""
from ko_pii.core.types import DetectionResult, RiskLevel

LABEL = "MY_CATEGORY"
LEGAL_BASIS = "관련 법조항"
CATEGORY = "분류"

_PATTERN = re.compile(r"...")

def detect(text: str) -> Iterator[DetectionResult]:
    for m in _PATTERN.finditer(text):
        yield DetectionResult(...)
```

체크리스트:
- [ ] `legal/mapping.py` 에 법조항·카테고리·위험도 매핑 추가
- [ ] `modes/redact.py` 에 한글 라벨 추가
- [ ] `detect.py` DETECTORS 튜플에 등록
- [ ] 최소 10개 테스트 케이스 (positive·negative·structure)
- [ ] 합성기 (`eval/synth.py`) 에 신규 카테고리 반영 (선택)

### 3. 새 입력 포맷

`src/ko_pii/io_/` 의 기존 reader (예: `docx.py`) 레퍼런스. `dispatcher.py`
확장자 매핑 추가.

### 4. 외부 도구 통합

`src/ko_pii/integrations/base.py` 의 `SecondaryDetector` 프로토콜 구현:

```python
class MyExternalDetector:
    name = "my-tool"
    def detect(self, text: str) -> Iterator[DetectionResult]:
        ...
```

옵셔널 의존성은 `pyproject.toml` extras 로 분리.

### 5. 버그 수정 / 정밀도 개선

- KLUE-NER FP/FN 분석으로 룰 보강
- 합성 회귀 (F1=1.000) 유지 확인 필수
- 새 룰은 `tests/unit/patterns/test_boundary_rules.py` 에 회귀 케이스 추가

## 핵심 원칙 (반드시 준수)

핵심 설계 원칙:

1. **No ML in core** — 코어는 Python 표준 라이브러리만 사용. 외부 ML 의존성은
   `integrations/` + `[ml]` extras 로만.
2. **한국 공공 부문 특화** — 일반 PII 도구보다 한국 도메인 fit 우선.
3. **법적 근거 부착** — 새 카테고리는 `LEGAL_BASIS` 명시 (감사 추적).
4. **가역 가명화 기본** — Vault 분리 보관 원칙.
5. **위험도 명시** — 5단계 RiskLevel 분류 부착.
6. **사용자 도메인 입력 존중** — 사전 큐레이션은 PR 작성자가 출처 명시.

## 테스트

```bash
pytest -q                                      # 전체 테스트
pytest tests/unit/patterns/test_rrn.py -v      # 특정 모듈
python -m ko_pii.eval.benchmark -n 60 --seed 0  # 합성 코퍼스 벤치마크
```

PR 전 모든 테스트 통과 + 합성 코퍼스 F1=1.000 유지 확인.

## Git 컨벤션

### 브랜치
- `main` — 안정 브랜치 (보호됨)
- `feature/<짧은 설명>` — 기능 PR
- `fix/<짧은 설명>` — 버그 PR

### 커밋 메시지

```
<스코프>: <70자 이내 요약>

- 변경 요점 1
- 변경 요점 2
- 테스트 카운트 변경 (필요 시)
```

스코프 예: `patterns/medical`, `dictionaries/surnames`, `vault`, `cli`, `docs`.

## PR 체크리스트

- [ ] 테스트 통과 (`pytest -q`)
- [ ] 합성 코퍼스 F1=1.000 회귀 없음
- [ ] 새 카테고리는 법적 근거·위험도·테스트 모두 포함
- [ ] 새 의존성은 extras 로 분리 (코어 deps 0개 원칙)
- [ ] 문서 업데이트 (docstring + 필요 시 docs/)
- [ ] CHANGELOG.md `[Unreleased]` 에 항목 추가

## 행동 강령

상호 존중 + 건설적 토론. 도메인 전문성 (한국 공공 부문) 을 가진 기여자가 많아
사용자 입력은 신중히 검토. 도메인 판단이 갈리면 GitHub Issue 로 공개 논의.

## 라이센스

기여 시 Apache-2.0 라이센스에 동의로 간주 (CLA 별도 없음).

## 도움 요청

- 일반 질문: GitHub Discussions
- 버그 리포트: GitHub Issues
- 보안 취약점: 비공개로 modak000 에게 직접 (이메일 README 참조)
