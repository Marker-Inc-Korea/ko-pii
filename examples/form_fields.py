"""Synthetic form and schema-aware table example; no extra dependencies."""
from ko_pii import Anonymizer
from ko_pii.tabular import anonymize_records


source = "성명: 김빛나라 **전화번호**: 010-1234-5678 생년월일(양력): 1988-01-01"
masked = Anonymizer(strategy="redact").process(source).text
assert masked == "성명: [성명] **전화번호**: [전화번호] 생년월일(양력): [생년월일]"
print(masked)

rows = [{"성명": "John Smith", "생년월일": "1988-01-01", "ｅｍａｉｌ": "demo@example.com", "비고": "public"}]
output, vault = anonymize_records(rows)
assert output == [{"성명": "<PERSON_1>", "생년월일": "<DT_BIRTH_1>", "ｅｍａｉｌ": "<EMAIL_1>", "비고": "public"}]
assert vault.reveal("<DT_BIRTH_1>") == "1988-01-01"
assert rows[0]["생년월일"] == "1988-01-01"
print(output)
