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
