# 파일 처리와 실패 상태

1.17부터 CLI와 `process_paths()`는 별도 Python 프로세스에서 파일을 읽습니다. 기본값은
파일 16 MiB, 전체 ZIP 압축 해제량 64 MiB, 멤버당 16 MiB, 2,048개 멤버, 압축률 200,
추출 텍스트 2,000,000문자, 파일당 30초입니다. Linux에서는 추출 프로세스의 주소 공간도
512 MiB로 제한합니다. Windows·macOS에서는 파일·시간 제한이 적용되지만 메모리 상한은
강제하지 않습니다. OS 권한을 격리하는 보안 샌드박스는 아닙니다.

```bash
ko-pii notice.hwpx --strategy redact --output notice.txt \
  --max-file-bytes 8388608 --max-decompressed-bytes 33554432 \
  --max-text-chars 500000 --extraction-timeout 15 --json-summary

ko-pii ./incoming --batch --output-dir ./processed \
  --extraction-timeout 30 --workers 2 --json-summary
```

`--json-summary`의 오류에는 `file_too_large`, `compression_ratio_exceeded`,
`extract_timeout`, `pdf_extraction_incomplete` 같은 코드가 포함됩니다. 단일 파일 실패는
종료 코드 1이며 가명화 출력과 Vault를 쓰지 않습니다. 배치는 실패한 파일을 결과 목록에
남기고 다른 파일을 계속 처리하되 하나라도 실패하면 종료 코드 1을 반환합니다.

표준 입력 `-`에도 바이트·문자 수 제한이 적용됩니다. 입력이 도착하기를 기다리는 시간은
파일 추출 timeout과 별개입니다. 파일마다 프로세스 시작 비용이 있으므로 수많은 작은
텍스트의 메모리 내 처리가 목적이면 `Anonymizer.process(text)`를 직접 사용합니다.

## HWPX 혼합 텍스트

1.22.14부터 `<hp:t>email:<hp:tab/>first@example.com</hp:t>`처럼 텍스트와
제어 요소가 교차하는 경우에도 뒤쪽 문자열을 누락하지 않습니다. `hp:t`가 가진 첫 텍스트와
자식 요소 뒤의 텍스트를 문서 순서로 읽습니다. 같은 구조가 본문·표·머리말 안에 있어도
중복 없이 처리하며, 텍스트 바깥의 XML 들여쓰기와 속성값은 본문으로 읽지 않습니다.

저수준 추출은 `tab`을 탭, `lineBreak`를 개행, `nbSpace`를 U+00A0,
`fwSpace`를 U+3000, `hyphen`을 U+00AD로 표현합니다. 상위 reader/CLI의 탐지용
정규화는 이후 별도로 적용됩니다. 이는 평문 변환 규칙이지 글꼴별 공백 너비나 화면 배치의
재현이 아닙니다. 형광펜/제목/변경 이력 표시 태그는 문자를 추가하지 않고 양쪽 텍스트를
연결합니다. 변경 이력의 채택·기각을 판단하거나 편집기에서 보이는 최종 화면을 복제하지는
않으므로, 문서 이력 정리가 필요한 경우 입력 전에 작성 도구에서 확정해야 합니다.

혼합 텍스트 구조는 [한컴의 HWPX 파싱 설명](https://tech.hancom.com/python-hwpx-parsing-2/)에
제시되어 있습니다. 복구된 문자열도 기존 `max_text_chars` 제한에 포함되며, 뒤쪽 섹션이
잘못된 XML이면 기존처럼 문서 전체를 실패시킵니다. 원본 HWPX 자체의 가명화, 미지원
속성/개체/이미지까지의 완전한 추출 또는 OCR은 제공하지 않습니다.

## CSV/XLSX를 표로 읽을 때

`ko_pii.io_.read_records()`는 CSV/TSV/XLSX의 표 데이터를 반환하는 저수준 Python API입니다.
XLSX는 시트마다 첫 비어 있지 않은 행을 헤더로 읽으며 셀 내부 탭/줄바꿈과 원래 열의
대응을 유지합니다. 여러 시트의 레코드를 하나의 목록으로 반환하므로 시트 ID가 필요한
애플리케이션은 별도 처리가 필요합니다. 시트 열거는 지원 XML 파일 이름 순서이며 통합문서
표시 순서/관계 검증까지 제공하지 않습니다.

1.22.13부터 Transitional 및 Strict SpreadsheetML의 텍스트 셀을 읽습니다.
시트의 `worksheet`와 공유 문자열의 `sst` 루트에서 네임스페이스를 선택하고, 공유 문자열,
inline/rich text 및 저장된 `<v>` 값을 동일 경로로 추출합니다. 알 수 없는 네임스페이스나
루트는 빈 시트로 간주하지 않습니다. 표 API는 오류를 반환하고, 텍스트 API/CLI는 기존
`document_extraction_incomplete` 실패 경로를 사용합니다. 인식 가능한 빈 시트는 기존처럼
비어 있는 것으로 처리합니다. 전체가 빈 문서이면 bounded/CLI의 빈 추출 거부도 유지됩니다.

Strict 네임스페이스는 [ECMA-376 Part 1](https://ecma-international.org/publications-and-standards/standards/ecma-376/)
배포본의 `OfficeOpenXML-XMLSchema-Strict.zip/sml.xsd`에 정의된
`http://purl.oclc.org/ooxml/spreadsheetml/main`을 사용합니다. Transitional은 기존
`http://schemas.openxmlformats.org/spreadsheetml/2006/main`입니다.
이는 셀 추출의 호환성 보완이며 OOXML 전체 스키마/패키지 적합성 인증이 아닙니다.
수식은 실행하지 않고 저장된 값만 읽으며 Excel의 표시 서식, 이미지/도형/주석 같은
미지원 부분을 모두 추출한다고 보장하지 않습니다.

1.22.3부터 중복 또는 빈 헤더는 오류입니다. XLSX 헤더 이후의 추가 셀에 값이 있으면
잘라내지 않고 실패합니다. 끝쪽의 빈 서식 셀과 비어 있는 행은 무시하고, 값이 없는 일반
셀은 빈 문자열로 채웁니다. 시트 중 하나라도 실패하면 부분 레코드 목록을 반환하지 않습니다.
CSV의 초과 셀은 기존처럼 `None` 키의 목록에 남으며 `anonymize_records()`에서 자동 탐지합니다.

1.22.8부터 UTF-8 BOM을 파일 서명으로 처리하여 첫 헤더에 붙이지 않습니다. BOM 때문에
`email`/`성명` 같은 첫 열이 다른 이름으로 읽혀 자동 매핑에서 빠지는 문제를 수정했습니다.
닫히지 않은 인용 셀이나 닫는 따옴표 뒤의 잘못된 문자는 `ValueError`로 거부하며,
앞선 정상 행만 부분 반환하지 않습니다. 표준 `""` 따옴표 이스케이프, 셀 내부 구분자와
줄바꿈, CR/LF/CRLF 행 구분은 보존합니다. 구분자/인용 문자는 기존처럼 표본에서 추론하며
모든 사용자 정의 CSV dialect나 잘못 구성된 스키마를 자동 복구하는 기능은 아닙니다.

표의 매핑된 열만 강제 가명화되며 비매핑 일반 열까지 자동 보호하지는 않습니다.
이 API는 현재 프로세스에서 실행되므로 신뢰하지 않는 파일의 자원 제한은 호출자가
담당해야 합니다. CLI의 격리된 평문 추출 경로와 혼동하지 마십시오.

1.22.4부터 명시적 `column_map`에 어느 행에도 존재하지 않는 열이 있으면 변환/Vault
쓰기 전에 `ValueError`를 반환합니다. 키가 서로 다른 행은 전체 키의 합집합을 기준으로
검사합니다. 빈 매핑 `{}`의 원문 유지 동작과 빈 레코드 목록은 그대로 지원합니다.
공통 스키마 매핑을 여러 표에 적용한다면 의도적으로 적용할 실제 열을 먼저 선택하세요.

### 표 API의 셀 타입

1.22.9부터 `anonymize_records()`는 모든 행의 구조와 매핑된 셀 타입을 변환 전에 검사합니다.
매핑된 개인정보 셀은 문자열·정수·null만 허용합니다. 정수는 `0`도 빠짐없이 문자열로
바꿔 선택한 전략을 적용하며, AUDIT에서는 원래 정수 타입을 유지하고 Vault에 쓰지 않습니다.
빈 문자열과 null은 그대로 둡니다. 명시적 필드 단언은 번호 유효성 검사가 아닙니다.

```python
from ko_pii.tabular import anonymize_records

rows, vault = anonymize_records(
    [{"account": 0, "count": 3}], column_map={"account": "ACCOUNT"},
)
assert rows == [{"account": "<ACCOUNT_1>", "count": 3}]
assert vault.reveal("<ACCOUNT_1>") == "0"
```

정수 `12345`와 문자열 `"12345"`는 같은 원문으로 취급합니다. `"0012345"`처럼 문자열에
남아 있는 선행 0은 보존하지만, 상위 시스템에서 이미 숫자로 바꿔 잃은 0은 복구하지 않습니다.
계좌·전화 식별자는 가능하면 입력 단계부터 문자열로 보관하세요.

매핑된 열의 bool/float/목록/객체는 오류입니다. 목록을 일반 탐지로 우회하거나 `0`을
빈 값처럼 통과시키지 않습니다. 비매핑 열은 문자열·정수·유한 float·bool·null을 그대로
보존합니다. 중첩 목록/객체는 [JSON API](STRUCTURED_PROCESSING.md)를 사용해야 합니다.
`None` 키만 CSV 초과 셀용 목록(문자열/null)을 허용하며 문자열은 기존처럼 일반 탐지합니다.
이 초과 셀에는 열 라벨 단언이 없으므로 모든 개인정보의 제거를 보장하지 않습니다.

잘못된 행/열 타입, 셀 타입, 정수 변환 한도 또는 매핑 라벨의 토큰 구분자/개행 오류는
앞선 정상 행을 변환하거나 Vault에 쓰기 전에 실패합니다. 오류 메시지는 행 번호만 담고
원문 값·열 이름을 복사하지 않습니다. 사용자 정의 라벨 자체는 계속 사용할 수 있습니다.
입력 객체는 수정하지 않으며 빈 입력에서도 전략 설정을 검사합니다.
이는 입력 사전 검사이지 Vault/감사 저장소 장애까지 되돌리는 트랜잭션이 아닙니다.
처리 도중 저장소가 실패하면 앞서 저장한 매핑이 남을 수 있고 부분 결과는 반환하지 않습니다.

`FileReadPolicy`의 바이트/개수/문자 제한은 양의 정수만, 압축률은 1 이상 유한수만 받습니다.
NaN/Infinity, 숫자 문자열, 정수 제한에 대한 bool/float는 거부합니다. ZIP 내부 XML의
DTD는 UTF-8/UTF-16 등 파서가 지원하는 인코딩과 관계없이 선언 단계에서 거부합니다.
일반 XML 문법/인코딩 오류는 기존 형식별 추출의 구성요소 실패 정보로 보고합니다.

## 평문 인코딩과 실패 처리

TXT/MD/LOG 및 CSV/TSV 파일은 UTF-8(시작 BOM 허용), CP949, EUC-KR 순으로
손실 없는 디코딩을 시도합니다. 시작 BOM이 UTF-8을 명시하면 다른 인코딩으로 우회하지
않습니다. 시작 서명만 제거하며 본문에 원래 있던 U+FEFF/U+FFFD 문자는 이 단계에서
삭제하지 않습니다. 이후 탐지용 정규화는 별도 처리입니다.

1.22.8부터 지원 인코딩으로 읽을 수 없는 바이트를 `�`로 바꿔 성공 처리하지 않습니다.
저수준 `read_text()`/`read_records()`는 `ValueError`를, bounded/isolated 및 CLI는
`text_decode_failed`를 보고합니다. CLI는 결과와 Vault를 쓰기 전에 중단하고, 배치는
해당 파일을 실패로 기록하면서 다른 정상 파일을 처리합니다. 기존 출력 파일이 있다면
삭제/덮어쓰기하지 않으므로 디렉터리 존재 여부 대신 종료 코드와 결과 목록을 확인하세요.

BOM 없는 인코딩 추론은 작성자의 실제 의도를 보증하지 않습니다. 바이트가 여러 인코딩에
동시에 유효할 수 있습니다. 원본 인코딩을 아는 애플리케이션은 먼저 해당 인코딩으로 엄격히
디코딩하고 문자열 API를 사용하거나 UTF-8로 변환하십시오. UTF-16/32 자동 처리나 깨진
바이트 복구는 제공하지 않습니다. JSON/JSONL 파일은 별도 UTF-8 입력 경로를 사용합니다.

## PDF 처리 범위

PDF는 텍스트 레이어를 검사합니다. 페이지 추출 예외나 텍스트가 없는 페이지를 발견하면
문서 전체를 실패로 처리합니다. 진짜 빈 페이지와 스캔 이미지 페이지를 자동 구분하지
않으므로 실패한 페이지와 텍스트가 없는 페이지 번호를 확인하고 OCR 또는 수동 검토를
수행하십시오. 일부 텍스트가 있는 페이지에도 이미지 속 개인정보가 남아 있을 수 있습니다.

직접 부분 추출 내용을 검토하려면 다음 API를 사용합니다. 반환된 부분 텍스트를 완전한
가명화 입력으로 취급하지 마십시오.

```python
from ko_pii.io_.pdf import inspect_text

result = inspect_text("document.pdf")
print(result.page_count, result.failed_pages, result.empty_pages)
```

이 저수준 API는 호출 프로세스에서 실행됩니다. 제한된 추출이 필요하면 다음을 사용합니다.

```python
from ko_pii.io_ import read_text_isolated

document = read_text_isolated("document.pdf", timeout=20)
text = document.text
```

`read_text_bounded()`의 기본 허용 포맷은 그대로 유지되며 PDF·구형 HWP는 제외합니다.
`read_text_isolated()`는 격리된 worker에서 두 포맷을 포함한 지원 포맷을 처리합니다.

## 저장 순서와 재실행

단일 파일 CLI는 감사 기록 확정, Vault 저장, 결과 출력, 리포트 저장 순서로 실행합니다.
Vault 저장이 실패하면 결과를 출력하지 않습니다. Vault가 저장된 뒤 출력이 실패하면
추가 매핑이 Vault에 남을 수 있지만, 기존 매핑은 유지됩니다.

Vault·결과·리포트 파일은 같은 디렉터리의 임시 파일에 작성하고 flush/fsync 후 교체합니다.
POSIX에서는 새 파일 권한이 0600입니다. 교체 전 오류가 나면 기존 파일을 유지합니다.
여러 파일을 하나의 트랜잭션으로 저장하거나 동시 writer를 잠그지는 않으므로 같은 Vault를
수정하는 실행은 직렬화하십시오. 디렉터리 fsync 및 정전 시 최종 rename의 내구성 보장은
제공하지 않습니다.

입력·출력·Vault·감사 로그·리포트에 같은 파일을 지정할 수 없습니다. 심볼릭 링크 출력도
거부합니다. 배치 결과 폴더는 입력 경로와 같거나 그 상위 폴더일 수 없습니다.
입력 폴더 하위에 둔 결과 폴더는
재실행할 때 다시 수집하지 않습니다.

배치에서 Vault·감사·ML 옵션과 단일 파일용 출력/리포트 옵션은 지원하지 않습니다.
해당 옵션을 지정하면 조용히 무시하지 않고 오류로 종료합니다.

## 1.18 실패 보고와 부분 문서

DOCX/HWPX/XLSX의 머리말·섹션·시트 등 지원 텍스트 구성요소 중 하나라도 파싱에 실패하면
기본 `read_text()`와 CLI는 `document_extraction_incomplete` 오류를 반환합니다.
실패 사유에는 원문이나 파서 예외 본문을 복사하지 않습니다. JSON의
`extraction_coverage`와 배치 각 결과의 `coverage`에는 읽은/빈/실패한 구성요소가 표시됩니다.
`complete`는 압축 파일에서 발견한 지원 텍스트 구성요소 추출에 한정되며 이미지 OCR이나
미지원 부분까지 검사했다는 뜻이 아닙니다. 패키지의 관계/manifest를 전부 검증하는 기능은
아니므로 참조는 있지만 파일 자체가 없는 시트 등의 손실까지 보장하지 않습니다.
`scope`와 `limitations`에도 이 경계를 표시합니다. 구성요소 이름과 입력 경로 자체도
민감정보일 수 있습니다.

부분 내용을 직접 점검해야 할 때만 다음 저수준 API를 사용합니다. 이 API는 현재 프로세스에서
실행되므로 신뢰하지 않는 문서를 자원 제한 없이 전달하지 마십시오.

```python
from ko_pii.io_.docx import inspect_text

inspection = inspect_text("document.docx")  # hwpx/xlsx 모듈에도 동일 API 제공
print(inspection.coverage)
# inspection.text는 부분 텍스트일 수 있으므로 완전한 처리 결과로 배포하지 않습니다.
```

CLI의 운영 실패는 JSON에 `stage`, `error`, `vault_saved`, `output_state`를 남깁니다.
`output_state`는 `not_written`, `uncertain`, `written` 중 하나입니다. 결과 파일/표준 출력
쓰기 중 오류가 발생하면 일부 쓰기를 배제할 수 없으므로 `uncertain`으로 보고합니다.
보고서 저장만 실패했다면 결과는 이미 출력됐을 수 있습니다. 구문 오류나 경로 충돌 등
argparse 인자 검증 오류는 기존 사용법 안내와 종료 코드 2를 사용합니다.

명시한 입력 파일 누락, glob 불일치, 빈 입력 폴더는 배치 실패로 보고됩니다.
빈 폴더/glob 불일치를 허용할 때만 `--allow-empty` 또는 Python `allow_empty=True`를
지정합니다. 이 옵션도 명시적 파일 누락을 숨기지 않습니다. 지원하지 않는 확장자는
폴더 탐색 중에는 `skipped`로 보고하지만 명시적으로 지정한 파일이면 실패입니다.

배치 JSON의 `results`는 입력-출력 대응표이기도 합니다. 실패한 실제 파일 경로만 추려
재시도할 수 있습니다. `file_unavailable`은 경로 수정/복구, `glob_no_matches`와
`no_input_files`는 입력 조건 수정을 먼저 해야 합니다. 이전 실패 보고서의 경로를 자동으로
신뢰해 실행하지 말고 원래 허용했던 작업 경로인지 확인하십시오.

```bash
ko-pii ./incoming --batch --output-dir ./processed --json-summary 2> batch-result.json
```

stderr 리디렉션 파일은 입력 폴더 밖에 두십시오. 보고서 자체가 다음 입력에 포함되는 것을
방지하기 위해서입니다. 병렬 처리는 작업 내부의 출력 이름 충돌을 방지하지만 서로 다른
배치 프로세스가 같은 결과 폴더를 동시에 갱신하는 경우까지 잠그지는 않습니다.
