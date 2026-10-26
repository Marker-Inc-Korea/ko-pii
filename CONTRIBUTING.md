# Contributing to ko-pii

## 개발 환경

Python 3.10 이상을 사용합니다. CI의 도구 버전과 검사 정의는
[checks.yml](.github/workflows/checks.yml)이 기준입니다.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,file,security]" "ruff==0.12.1" "mypy==1.17.1" "build==1.5.0" "twine==7.0.0"
python -m pytest -q
python -m ruff check src tests scripts examples
python -m mypy
python scripts/audit_research.py
python -m build
python -m twine check dist/*
```

Windows 가상환경 활성화는 `.venv\Scripts\Activate.ps1`입니다.
테스트 수와 실행 시간은 환경·선택 의존성에 따라 달라지므로 고정 숫자를 통과 조건으로
삼지 않습니다. RAG 어댑터는 `.[dev,langchain,llamaindex]` 설치 환경에서 따로 검사합니다.
torch 기반 선택 모듈 전체를 기본 CI가 검증한다는 뜻은 아닙니다.

## 설치본 검증

소스에서 성공해도 wheel에서 파일이 누락될 수 있습니다. 별도 가상환경에 빌드한 wheel과
dev/file/security extras를 설치하고 아래 검사를 실행하세요. `PYTHONPATH`는 비워둡니다.

```bash
python -m pytest --import-mode=importlib -o pythonpath= -q
python scripts/check_examples.py --require-installed
```

두 번째 명령은 README의 Python 예제가 실행 파일과 같은지 확인하고 Python·텍스트 CLI·
JSON CLI 예제를 실행합니다. 모든 문서의 임의 코드 블록을 자동 실행하는 검사는 아닙니다.
빌드 디렉터리를 다시 쓸 때는 이전 릴리스 파일이 섞이지 않게 별도 작업 디렉터리를 사용하세요.

## 탐지 변경

- 실제 개인정보 대신 합성 최소 재현 입력과 기대 span을 제출합니다.
- 미탐을 잡는 양성 사례와 새 오탐·경계·정규화 사례를 함께 테스트합니다.
- 새 라벨은 `src/ko_pii/labels.py`, 탐지기 등록, 위험도·표시 이름·처리 정책을 함께 확인합니다.
- 사용자 규칙은 기존 `RegexDetector`, `LiteralDetector`, `SecondaryDetector` 확장 지점을 우선합니다.
- 런타임 의존성은 코어에 추가하지 않고 선택 extras로 분리합니다.
- 실제 출력에서 값이 남는지 확인합니다. 탐지 성공과 완전한 치환은 다릅니다.
- 회귀셋으로 룰을 조정했다면 독립 검증이라고 부르지 않습니다.

CI의 합성 회귀 하한은 현재 seed 0~3, 각 60문서에 대해 micro precision 0.68,
recall 0.95, F1 0.80, macro F1 0.60입니다. 이는 특정 생성기의 회귀 기준이며
실제 고객 문서 정확도의 보증도, F1=1.000 요구도 아닙니다.

```bash
python -m ko_pii.eval.benchmark -n 60 --seed 0 --min-micro-precision 0.68 --min-micro-recall 0.95 --min-micro-f1 0.80 --min-macro-f1 0.60
```

## 호환성

[호환성 정책](docs/COMPATIBILITY.md)에 맞춰 공개 API와 저장 형식을 변경합니다.
`tests/contracts/fixtures/1.22.0.json`은 실제 배포된 1.22.0에서 생성한 합성 fixture입니다.
검사가 실패한다고 새 버전 출력으로 덮어쓰면 호환성 검사가 무의미해집니다.
지원 기준을 늘릴 때 별도 파일을 추가하고 생성 버전과 패키지 해시를 남기세요.

## 연구 자료

`data/`의 과거 스크립트는 현재 제품 코드와 지원 범위가 다릅니다.
[연구 목록](research/README.md)은 구문 오류가 남은 파일까지 공개합니다.
자료 변경 시 출처·라이선스·SHA-256 목록을 의도적으로 갱신해야 합니다.
외부 평가에는 네트워크를 켜는 별도 명령이 필요하며 일반 CI가 데이터를 받지 않습니다.

## 릴리스

`pyproject.toml`, `ko_pii.__version__`, CHANGELOG의 버전을 맞춥니다.
main CI를 확인한 뒤 일치하는 `vX.Y.Z` 태그를 만듭니다.
release.yml은 공통 CI를 다시 호출하고, sdist에서 만든 wheel을 설치·검증합니다.
게시 job은 같은 실행의 artifact를 내려받아 버전·소스 커밋·해시를 확인한 뒤 게시합니다.
게시 단계에서 빌드를 다시 하지 않으며 OIDC 권한은 게시 job에만 부여합니다.

저장소 설정에서 `pypi` 환경 승인자 및 태그 제한을 운영자가 관리해야 합니다.
YAML 수정만으로 이 보호 설정이 자동 적용되지는 않습니다. 해시는 파일 동일성을
검사할 뿐, 악의적인 저장소 관리자나 손상된 runner를 막는 신뢰 경계는 아닙니다.

## 기여와 문의

작은 재현 테스트, 변경 근거, 사용자 영향, 문서·CHANGELOG 변경을 함께 제출하세요.
코드는 MIT로 기여하며 외부 데이터의 재배포 권리는 별도로 확인해야 합니다.
일반 문의는 GitHub Issues, 민감한 취약점은 [비공개 보고](SECURITY.md)를 사용합니다.
