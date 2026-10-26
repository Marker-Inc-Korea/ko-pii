# ko-pii

[한국어](README.md) · [PyPI](https://pypi.org/project/ko-pii/) · [Changelog](CHANGELOG.md)

Detect and pseudonymize personal information in Korean text.
The core uses rules, dictionaries and format validation, with no model download or external API.
Python 3.10+, MIT-licensed code, zero core runtime dependencies.

## Quick Start

```bash
python -m pip install ko-pii
```

This exact [example](examples/quickstart.py) is executed against the installed wheel in CI.

```python
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
```

Tokenization moves originals into a Vault; it does not destroy them. Code with access to the
Vault can restore values. Store it separately from outputs. Authentication and authorization
belong to the calling application.

## Scope

- 33 labels covering Korean structural identifiers, names, addresses and related fields.
- Tokenization, partial masking, redaction and per-label processing policies.
- JSON/JSONL field and array rules, including explicit field-label assertions.
- Reusable `PolicyProfile`, before/after policy comparisons and value-free explanation reports.
- `LiteralDetector` for known values, plus regex and callback extension points for trusted code.
- Optional document processing and encrypted Vault storage. ML/RAG adapters are extras, not core requirements.

See the [changelog](CHANGELOG.md) for the exact scope of each release.

## CLI and Reusable Policies

The repository includes a [policy](examples/policy.json) for STRICT/redact on EMAIL and PHONE.
Run these examples from the repository root after installation:

```bash
ko-pii examples/input.txt --policy examples/policy.json --output masked.txt
ko-pii examples/request.json --format json --policy examples/policy.json --output masked.json
```

Use `ko-pii --help` for options. See [profiles](docs/POLICY_PROFILES.md) and
[structured processing](docs/STRUCTURED_PROCESSING.md) for field-level settings.
Detailed guides currently contain Korean explanations with executable Python/CLI examples.

## Before Deployment

No guarantee of complete PII removal, legal anonymity or compliance is made.
Even format/checksum-based detection can miss values or produce false positives.
Names and unstructured addresses are especially domain-dependent.
Risk levels are supporting heuristics, not legal determinations.

Evaluate the labels relevant to your own documents, and measure **actual output retention**
separately from detection accuracy. A few dozen successful samples do not statistically
establish a low leakage rate. Apply your own review and approval policy before public release
or external transmission. Do not include real personal data in issues or tests.

The [external evaluation protocol and results](research/README.md) disclose dataset revisions,
label scope and sample selection. Historical F1/throughput figures describe their original
conditions, not the current release or a customer's environment.

## Documentation

| Need | Guide |
|---|---|
| Feature navigation | [Documentation index](docs/README.md) |
| Input formats and extraction limits | [File processing](docs/FILE_PROCESSING.md) |
| Vault, keys and authorization boundary | [Vault security](docs/VAULT_SECURITY.md) |
| Custom rules and traces | [Extensions](docs/SCOPED_RULES_AND_TRACE.md) |
| Domain evaluation and regression comparison | [Evaluation](docs/DOMAIN_EVALUATION.md) |
| API, CLI and storage compatibility | [Compatibility policy](docs/COMPATIBILITY.md) |
| Development and release checks | [Contributing](CONTRIBUTING.md) |
| Private vulnerability reports | [Security policy](SECURITY.md) |

## Maintenance Boundaries

CI checks Ubuntu Python 3.10/3.12/3.14, Windows/macOS CLI behavior, and optional RAG adapters.
Release tags run the same validation; only the tested distribution files are published.
These checks validate package behavior, not universal PII removal performance.

`src/` is product code; `tests/` and `examples/` are maintained verification assets.
Historical research in `data/` has an explicit [inventory](research/catalog.json) and is not
shipped on PyPI. Data licenses are separate from the code's MIT license.
The previous long introduction remains in the
[1.22.0 README](https://github.com/Marker-Inc-Korea/ko-pii/blob/v1.22.0/README.en.md).
