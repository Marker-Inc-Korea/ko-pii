# 재사용 정책과 알려진 값 탐지

1.22의 선택 기능입니다. 기존 `Anonymizer` API와 기본 동작은 그대로이며, 새 런타임
의존성이나 모델 다운로드는 없습니다.

## 한 설정을 Python과 CLI에서 사용하기

```python
import json
from pathlib import Path
from ko_pii import PolicyProfile

profile = PolicyProfile({
    "mode": "STRICT",
    "strategy": "redact",
    "include": ["EMAIL", "PHONE"],
    "strategies": {"PHONE": "partial"},
}, name="contact-preview")
print(profile.process("a@example.com / 010-2345-6789").text)
print(profile.fingerprint)
Path("policy.json").write_text(json.dumps(profile.to_dict(), ensure_ascii=False), encoding="utf-8")
```

```bash
ko-pii input.txt --policy policy.json --output masked.txt
ko-pii records.json --format json --policy policy.json --output masked.json
ko-pii records.jsonl --format jsonl --policy policy.json --output masked.jsonl
ko-pii-compare-policies input.txt --before policy.json --after proposed.json --output comparison.json
```

`PolicyProfile.from_json(text)`와 `from_dict(mapping)`으로 읽습니다. 프로필 파일 형식은
`{"schema_version":1,"name":"...","settings":{...}}`이며 기존 미리보기용 설정 객체도
받습니다. 이름은 표시용이며 설정 해시에 포함하지 않습니다. 내보낸 객체를 수정해도
원래 프로필은 바뀌지 않습니다.

지원 설정은 `mode`, `strategy`, `strategies`, `include`, `exclude`, `person_exclusions`,
`field_labels`, `field_rules`, `field_person_exclusions`입니다. 필드 설정은
[구조화 처리](STRUCTURED_PROCESSING.md)의 JSON 형태를 그대로 사용합니다.
필드가 있는 프로필은 `process_json(data)` / `process_jsonl(text)` 또는 CLI JSON 모드를
써야 하며 텍스트 모드에서 무시하지 않습니다. JSON 미리보기에는 `--format json`을 씁니다.

CLI의 `--policy`와 `--mode`, `--strategy`, `--include`, 필드 옵션, ML 옵션 등은 함께
쓸 수 없습니다. 우선순위를 추측하지 말고 프로필을 수정하세요. 파일 읽기 제한, 출력,
Vault, 설명/추적 옵션은 함께 사용할 수 있습니다. 배치 `--batch`에서는 지원하지 않습니다.
프로필은 실행 코드, 모델, 사용자 regex, Vault·키 또는 파일 경로를 불러오는 기능이 아닙니다.

`process*()` 호출마다 새 Anonymizer와 메모리 Vault를 사용합니다. 여러 호출에서 동일한
토큰을 유지하려면 `profile.make_anonymizer(vault=...)`로 생성한 객체를 재사용하세요.
이 메서드는 **코어 설정만** 적용합니다. 구조화 필드까지 재사용하려면
`anonymize_json(data, anonymizer=anon, **profile.structured_options())`를 사용하세요.
프로필의 `repr`에는 설정을 표시하지 않지만, 내보낸 JSON에는 제외어와 필드명이 포함됩니다.
이를 개인정보 없는 파일이나 권한 관리 수단으로 취급하지 마세요. 해시도 승인/서명이 아닙니다.

## 이미 아는 값만 추가하기

```python
from ko_pii import Anonymizer, LiteralDetector

known = LiteralDetector({"PERSON": ["김도구"], "EMAIL": ["local@intranet"]}, boundary="korean")
anon = Anonymizer(secondary_detector=known)
print(anon.process("김도구에게 local@intranet 주소로 연락").text)
```

- `word`(기본): 값 앞뒤가 Unicode 단어 문자와 붙어 있지 않아야 합니다.
- `substring`: 부분 문자열도 탐지합니다. 짧은 값은 오탐을 늘릴 수 있습니다.
- `korean`: word 경계에 더해 한글로만 된 PERSON 뒤의 제한된 조사 목록을 허용합니다.
  `김도구에게`는 이름만, `김도구리`는 탐지하지 않습니다. 모든 복합 조사나 형태소 분석을
  지원하는 것은 아닙니다. 다른 라벨/영문 값에는 word 경계를 적용합니다.

원문의 정확한 대소문자/코드 포인트로 비교합니다. 전각 문자, zero-width 삽입, 철자 변형을
이 탐지기가 자동 정규화하지는 않습니다. 정규식 기호는 문자 그대로 취급합니다. 같은 시작점의
여러 값 중 경계가 유효한 가장 긴 값을 반환하며, 다른 시작점의 겹침은 기존 병합에서 처리합니다.

설정은 전체 1,024개 값(중복 포함), 값당 256자, 합계 65,536자까지입니다.
기본 입력 1,000,000자/결과 10,000건 제한은 생성자의 `max_chars`/`max_matches`로 바꿀 수
있으며 초과하면 조용히 자르지 않고 오류를 반환합니다. 동일 값에 서로 다른 라벨을 지정할 수
없습니다. 주민번호/이메일 등 올바른 기존 라벨만 사용하고 사번을 ACCOUNT로 위장하지 마세요.

추가 결과도 include/exclude, PERSON 제외어, 병합과 처리 모드의 적용을 받습니다.
알려진 값을 등록했다고 반드시 치환되는 것은 아니며 실제 출력으로 검증해야 합니다.
이 기능은 명단/값 사전이 있는 시스템의 확장 지점이지 미지의 인명 탐지나 익명성 보장이
아닙니다. 값 사전 자체도 민감정보이며 프로필 JSON에 함께 포함하는 기능은 제공하지 않습니다.
