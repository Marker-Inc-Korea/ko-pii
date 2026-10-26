from ko_pii import Anonymizer, ProcessingMode

result = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    include={"EMAIL", "PHONE"},
).process("Email: demo@example.com / Tel: 010-2345-6789")

print(result.text)
assert "demo@example.com" not in result.text
assert "010-2345-6789" not in result.text
assert result.vault.reveal("<EMAIL_1>") == "demo@example.com"
