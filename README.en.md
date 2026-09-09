**English** | [한국어](README.md)

# ko-pii

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/ko-pii.svg)](https://pypi.org/project/ko-pii/)
[![MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Demo](https://img.shields.io/badge/demo-HuggingFace-yellow.svg)](https://huggingface.co/spaces/modak000/ko-pii-demo)
[![Software: Stable](https://img.shields.io/badge/software-stable-1f6f43)](CHANGELOG.md)

**A Python library for detecting and reversibly pseudonymizing personal information (PII) in Korean documents.** Works with rules + dictionaries + checksums only, without any external ML dependency. Especially strong on public/administrative documents, and usable as a preprocessing layer in front of any ML pipeline.

> **Public measurements are distribution-specific evidence, not product
> qualification.** ko-pii measured F1 0.66 on 4,891 conversational KDPII
> documents and F1 0.79 on a 540-document administrative/form-like generated
> set. Results change with the dataset, label policy, and scorer, so these
> numbers are not a universal ranking or the expected accuracy of a customer
> deployment. See the [benchmark methodology](docs/BENCHMARK.md).

## Product Contract

| Item | Operating definition |
|---|---|
| Primary users | Privacy, data, and AI platform teams handling Korean public-sector or regulated documents |
| Customer job | Pseudonymize structural Korean PII before external transfer or indexing and control restoration |
| Product promise | Reproducible rule/dictionary/checksum detection and pseudonymization, plus Vault storage and audit-recording primitives |
| Not promised | General NER, equal accuracy on chat/social/news text, legal anonymity, or compliance certification |
| Go-live requirement | Measure label-level confusion counts on tenant documents and approve PERSON/ADDRESS handling |
| Status meaning | `Software: Stable` covers package maturity; every tenant remains unqualified until site evidence exists |

Critical identifiers and contextual labels such as PERSON and ADDRESS must not
be collapsed into one F1 for an operating decision. Tenant qualification must
evaluate critical leakage, contextual-label behavior, and Vault operations
separately.

```python
from ko_pii import Anonymizer, ProcessingMode

result = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize").process(
    "신청인 홍길동 (880101-1234568) 연락처 010-1234-5678"
)
print(result.text)
# 신청인 <PERSON_1> (<RRN_1>) 연락처 <PHONE_1>

print(result.vault.reveal("<RRN_1>"))            # 880101-1234568 (the application controls access)
print(result.combined_risk.combined_risk.name)   # CRITICAL
```

Do not scan transport chunks independently. Keep them behind the forwarding
boundary until the final decision:

```python
from ko_pii import PreForwardAnonymizer

stream = PreForwardAnonymizer(max_chars=100_000)
stream.feed("주민번호 880101-")
stream.feed("1234568 입니다")
safe_result = stream.finalize()  # feed() never returns source text
```

This API does not pretend to offer token-level low latency. An identifier can
cross any chunk boundary, so the privacy-safe default is to pseudonymize the
complete bounded message before forwarding it.

### Before / after pseudonymization

```
Original:
  신청인 홍길동 (880101-1234568) 연락처 010-1234-5678
  주소: 서울특별시 강남구 테헤란로 152

tokenize (token substitution + restorable via Vault):
  신청인 <PERSON_1> (<RRN_1>) 연락처 <PHONE_1>
  주소: <ADDRESS_1>

partial (mask only part — real-world form style):
  신청인 홍OO (880101-1******) 연락처 010-****-5678
  주소: 서울특별시 강남구 ***

redact (replace with category name):
  신청인 [성명] ([주민등록번호]) 연락처 [전화번호]
  주소: [주소]
```

> **New here?** If restoration is required, use `STRICT` + `tokenize`. Otherwise,
> use `STRICT` + `redact`, which stores no original-value mapping. A Vault is a
> separate PII store that requires its own protection.

### Things you might not expect

- **Catches names even with attached particles** — "홍길동이", "홍길동에게", "홍길동의" → the Korean particle is split off automatically, then PERSON is detected
- **Hanja annotation** — "홍길동(洪吉童)" → recognizes both the Hangul and the Hanja
- **Romanized names** — "Hong Gildong" → normalized to Hangul before matching
- **Direct HWP/HWPX/DOCX/PDF input** — `ko-pii report.hwp --strategy tokenize` (handles tables, headers, footers, and metadata)
- **Automatic CSV/XLSX header recognition** — headers like "성명/주민번호/연락처" → automatically mapped to PERSON/RRN/PHONE
- **Automatic rejection of administrative dates** — "시행일자: 2026-05-21", "감사기간: 3월~4월" → not birthdays (30+ non-birthday keywords)
- **Automatic rejection of pseudonymized notations** — "박씨", "김모씨", "○○○ 시민" → already pseudonymized (not PII)
- **Automatic combined-risk assessment** — a name alone may not be PII, but when *name + RRN + address* appear together → CRITICAL (quasi-identifier combination check per the "Guidelines on De-identification Measures for Personal Information")
- **Audit logging** — JSONL records of token operations with caller-supplied actor and context

---

## Table of Contents

1. [Why you need it](#why-you-need-it)
2. [Key features](#key-features)
3. [Installation](#installation)
4. [Usage scenarios](#usage-scenarios)
5. [Evaluation results](#evaluation-results)
6. [Usage](#usage)
7. [33 PII categories](#33-pii-categories)
8. [Detection policy — which prefixes and anchors work](#detection-policy--which-prefixes-and-anchors-work)
9. [Processing modes + substitution strategies](#processing-modes--substitution-strategies)
10. [Additional features](#additional-features)
11. [FAQ](#faq)
12. [Development](#development)
13. [License](#license)

---

## Why you need it

RAG/LLM pipelines index and retrieve raw, unstructured data and feed it directly into models — PII gets exposed on **both the vector DB and the response side**.

- **Legal obligation** — Personal Information Protection Act (PIPA): restrictions on processing sensitive information such as resident registration numbers and health information (also relevant for GDPR/HIPAA abroad)
- **Sovereignty / air-gapped networks** — public-sector network-separated environments cannot send PII to external APIs → **offline deterministic detection** is essential
- **Trust / reputation** — a single leak can destroy trust in a service
- **Complement to ML** — format- and checksum-valid identifiers can be
  validated deterministically, providing a precision-oriented layer alongside
  contextual ML. Actual F1 remains dataset- and format-specific

ko-pii blocks PII at **both ends of RAG — ingest (before entering the vector DB) and retrieval (before passing to the LLM)**. Within one Vault, it substitutes the same person with the same token to preserve context (with LlamaIndex/LangChain integrations provided), and supports restoration and audit recording. Authentication, authorization, and key management remain the calling application's responsibility.

---

## Key features

- **Korea-specific** — 33 categories of Korean PII (RRN, FRN, passport, business registration number, card, account, phone, email, address, vehicle, person, position, nationality, etc.). Especially strong on public documents
- **Deterministic detection** — rules + dictionaries + checksums produce
  reproducible decisions for format-valid RRN, card, and business identifiers
- **Evasion blocking** — neutralizes Unicode bypass tricks such as full-width digits (`０１０`) and zero-width character insertion via normalization (detection offsets are preserved against the original)
- **No external dependencies** — uses only the Python standard library. Runs offline / on air-gapped networks, no GPU required
- **Preprocessing layer** — emits standardized `DetectionResult` objects (label/start/end/text/confidence). Easy to slot in front of an ML pipeline
- **Reversible pseudonymization + Vault** — keeps the token ↔ original mapping in a separate store, restorable
- **Automatic legal-basis attachment** — each detection is automatically tagged with the relevant PIPA article (audit trail)
- **Diverse inputs** — TXT, CSV, XLSX, HWP, HWPX, DOCX, PDF (`[file]` extras)

### Per-domain usage guide

| Domain | Recommended setting | Notes |
|---|---|---|
| Public documents (official documents, civil petitions, HR) | `STRICT` + `tokenize` | Default. The best-fitting domain |
| LLM training-data preprocessing | `PARANOID` + `tokenize` or `redact` | Prioritize leak prevention |
| Pharma / bio | `STRICT` + `exclude={"AGE","HEIGHT","WEIGHT"}` | Avoid false positives on usages like "per 1 kg of body weight" |
| Finance / insurance | `STRICT` + `tokenize` | Deterministic detection of RRN/card/account |
| General office (internal documents) | `BALANCED` + `partial` | Readable partial masking |

```python
# Pharma domain — prevent PERSON FP + body-attribute false positives
anon = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    exclude={"AGE", "HEIGHT", "WEIGHT"},  # avoid false positives like "per 1 kg of body weight"
)

# Apply exclusions only to this project; do not modify the package dictionary
anon = Anonymizer(
    mode=ProcessingMode.STRICT,
    strategy="tokenize",
    exclude={"AGE", "HEIGHT", "WEIGHT"},
    person_exclusions={"이부프로펜", "한미약품", "메트포르민"},
)
```

---

## Installation

```bash
pip install ko-pii  # current PyPI stable

# To test the 1.16 API on main before its tagged release:
python3 -m pip install \
  "ko-pii @ git+https://github.com/Marker-Inc-Korea/ko-pii.git@main"
```

Extras (as needed):

```bash
pip install "ko-pii[file]"       # HWP/HWPX/DOCX/PDF
pip install "ko-pii[security]"   # Vault AES-256-GCM
```

**Python 3.10 or later.** The core uses only the standard library.

---

## Usage scenarios

### Scenario 1 — Bulk pseudonymization of approved official documents (before external release / sending to an LLM)

```python
import os
from pathlib import Path

from ko_pii import Anonymizer, ProcessingMode
from ko_pii.io_ import read_text
from ko_pii.vault.encrypted import save_encrypted

for path in Path("./공문서/").glob("*.hwp"):
    # Use one Vault per document to limit linkability and incident scope
    anon = Anonymizer(mode=ProcessingMode.PARANOID, strategy="tokenize")
    result = anon.process(read_text(str(path)))
    Path(f"./가명화/{path.stem}.txt").write_text(result.text, encoding="utf-8")
    save_encrypted(
        result.vault,
        f"./vault/{path.stem}.kvault",
        os.environ["KPII_VAULT_PASSWORD"],
    )
```

- **PARANOID mode** — conservatively handles LOW risk and above. It does not guarantee zero misses; validate it on the target document distribution before external transmission.
- Keep the pseudonymized result externally and the Vault in an internal store, separated
- HWP parsing and Vault encryption: `pip install "ko-pii[file,security]"`

### Scenario 2 — Up-front PII verification in a civil-petition response system

```python
from ko_pii import Anonymizer, ProcessingMode, RiskLevel

anon = Anonymizer(mode=ProcessingMode.AUDIT)  # no blocking, detection-only reporting

result = anon.process(incoming_petition_text)

# If the combined risk is CRITICAL, notify the handler
if result.combined_risk.combined_risk >= RiskLevel.CRITICAL:
    notify_admin(
        identifiers=result.combined_risk.distinct_identifiers,  # ["RRN"]
        quasi=result.combined_risk.distinct_quasi,              # ["ADDRESS", "PERSON", "PHONE"]
    )

# Give the responding staff a pseudonymized version
masked = Anonymizer(mode=ProcessingMode.STRICT, strategy="partial").process(
    incoming_petition_text
).text
```

- **AUDIT mode** — reports detections only, without blocking (for auditing / statistics)
- **Combined-risk** auto-assessment — quasi-identifier combination check per the "Guidelines on De-identification Measures for Personal Information"
- Provide responding staff with partial masking via the `partial` strategy (`880101-1******`)

### Scenario 3 — Automatic PII pseudonymization in Python logs (for developers)

```python
# Automatically pseudonymize whenever logger.info("...") is called anywhere in the code
import logging
from ko_pii import Anonymizer, ProcessingMode

_anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="redact")

class PIIFilter(logging.Filter):
    def filter(self, record):
        record.msg = _anon.process(str(record.msg)).text
        return True

logging.getLogger().addFilter(PIIFilter())
logging.info("신청인 홍길동 (880101-1234568) 처리 완료")
# → "신청인 [성명] ([주민등록번호]) 처리 완료"
```

---

## Evaluation results

### Headline benchmark — KDPII v1.1 test split

KDPII v1.1 test split: **4,891 human-labeled documents** of Korean everyday conversation. All systems are scored with a single canonical matcher (`ko_pii.eval.kdpii.match_forms_overlap`, substring set matching, position-agnostic), with `person_min_length=3` (1–2 character PERSON spans excluded). All three systems run on the same documents with the same matcher.

| System | Type | F1 | Precision | Recall |
|---|---|---:|---:|---:|
| **ko-pii** | Rules + dictionaries + checksums | **0.660** | 0.699 | 0.624 |
| Presidio (kr_adapt) | spaCy ko + regex | 0.273 | — | — |
| openai/privacy-filter | 660M transformer (ONNX) | 0.264 | — | — |

(TP/FP/FN — ko-pii: TP 813 / FP 350 / FN 489. Presidio: TP 220 / FP 85 / FN 1085. openai/PF: TP 294 / FP 634 / FN 1008.)

A generic Korean NER model (KoELECTRA NER) was **not measured** for this run (rough estimate ~0.10–0.15) and is therefore omitted from the headline table.

> **Fair comparison.** The aggregate F1 partly reflects that Presidio and openai/privacy-filter **lack many Korean PII categories entirely** (they emit 0 on AGE, POSITION, RRN, …). Even restricting to the categories each tool *does* support, ko-pii still leads — **vs openai/privacy-filter 0.61 : 0.37** (its 7 labels), **vs Presidio 0.87 : 0.65** (its 9 labels). The gap is not merely missing categories; ko-pii is also more accurate on common ground.

> **Honest framing.** KDPII is everyday conversational text. ko-pii is rule-based: it is strong on structural/deterministic PII and Korean administrative/form text, and weaker on free-form conversation (KDPII PERSON 0.135, ADDRESS 0.241). The project-built generated eval set below (540 admin/form-like documents, validated gold) scored 0.790. Its generator did not reference ko-pii rules, but this is not independent third-party validation and does not replace evaluation on customer documents.

### Deterministic / structural PII — ko-pii per-label F1 on KDPII

Checksum- and regex-verified categories reach near-perfect F1:

| Label | F1 | | Label | F1 |
|---|---:|---|---|---:|
| RRN | 1.000 | | VEHICLE | 0.980 |
| EMAIL | 1.000 | | WEIGHT | 0.952 |
| IP | 1.000 | | HEIGHT | 0.935 |
| FRN | 1.000 | | PASSPORT | 0.909 |
| PHONE | 0.992 | | AGE | 0.893 |
| | | | ACCOUNT | 0.819 |

### Speed (per document, measured)

1 unit = 1 CPU core.

| System | Latency / doc | Throughput | Hardware |
|---|---:|---:|---|
| ko-pii | 0.19 ms | ~5,350 docs/s | 1 CPU core |
| Presidio | 4.2 ms | ~238 docs/s | 1 CPU core |
| openai/PF (ONNX, CPU) | 481 ms | ~2 docs/s | 1 CPU core (bulk needs GPU) |

These systems used different active recognizers, models, and runtimes. The table
describes the measured configurations rather than a universal same-function speed
ranking.

### External API fee context

| System | Per-document external API fee |
|---|---:|
| **ko-pii core** | None |

Local CPU, storage, and operational costs are not zero and are excluded here.

### Reproduction

KDPII, 3-system run (ko-pii / openai-PF / Presidio):

```bash
python -m ko_pii.eval.model_comparison data/kdpii/test.json \
    --mode kdpii --include-presidio --backend onnx --person-min-length 3
```

### Supplementary results

> **Note.** The generated eval set below uses the **same** matcher as the headline table (directly comparable); KLUE-NER is from an earlier run with a different scorer (context only).

| Domain | ko-pii | openai/PF | Presidio |
|---|---:|---:|---:|
| Generated eval set (540 docs, admin/form-like, validated gold) | **0.790** | 0.451 | 0.483 |
| KLUE NER | **0.419** | 0.155 | 0.000 |

Full details: [`docs/BENCHMARK.md`](docs/BENCHMARK.md) and [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md).

> **Before production use:** 30–100 real documents are only an initial smoke and
> calibration sample for obvious integration errors and false positives/negatives.
> They do not establish statistical fitness or zero leakage. Before go-live, use a
> larger risk- and label-distribution-based frozen set, retain label-level TP/FP/FN,
> recall, and confidence intervals, then run shadow/canary checks. See
> [`docs/domain_fit_report.md`](docs/domain_fit_report.md).

### Known limitations

- **ko-pii is rule-based** — strong on structural/deterministic PII and Korean administrative/form text, weak on free-form conversation (KDPII PERSON 0.135, ADDRESS 0.241).
- **PERSON false positives (FP)** — the biggest weakness of rule-based PERSON detection. Domain vocabulary (e.g. pharma ingredient names) can be picked up as a person's name. Use `person_exclusions={...}`, turn PERSON off with `exclude={"PERSON"}`, or supply a trained token-NER hybrid.
- **Unstructured ADDRESS** — weak on unstructured addresses like "강남 쪽에 살아" (needs an anchor). Structured addresses ("서울특별시 강남구 테헤란로 152") are fine.
- Checksum-backed structural labels have stronger false-positive controls than format-only labels, but OCR, new separators, and unsupported real formats can still cause misses; validate recall separately.

Full evaluation: [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md).

---

## Usage

### CLI

```bash
# Basic
ko-pii input.txt --mode STRICT --strategy tokenize \
       --vault vault.json -o output.txt --report report.html

# Batch (whole directory, parallel)
ko-pii ./incoming/ --batch --workers 4 --output-dir ./anonymized/

# Vault encryption + audit log
KPII_VAULT_PASSWORD=secret ko-pii doc.hwp \
    --vault vault.kvault --audit-log audit.jsonl

# Per-project PERSON exclusions (UTF-8, one term per line; blanks/# comments ignored)
ko-pii doc.txt --person-exclusions-file tenant-person-exclusions.txt
```

`--batch` processes each file independently and does not support `--vault`,
`--vault-password`, or `--audit-log`. Combining those options is rejected instead
of being silently ignored. Use single-file mode when you need a reversible Vault
and audit trail. With `--json-summary`, warnings are included in the JSON
`warnings` array so the complete `stderr` stream remains one parseable object.
In this mode, use `KPII_VAULT_PASSWORD` instead of the interactive
`--vault-password` prompt.

### Python API

```python
from ko_pii import Anonymizer, ProcessingMode

anon = Anonymizer(mode=ProcessingMode.STRICT, strategy="tokenize")
result = anon.process(text)

print(result.text)                       # pseudonymized text
print(result.vault.reveal("<RRN_1>"))    # restore original (authorization is application-owned)
print(result.summary["by_label"])        # {"RRN": 1, "PHONE": 1, "PERSON": 1}
```

### Combined risk + k-anonymity

```python
# Automatic combined-risk assessment of detection results
print(result.combined_risk.combined_risk.name)    # CRITICAL
print(result.combined_risk.distinct_identifiers)  # ["RRN"]
print(result.combined_risk.distinct_quasi)        # ["PERSON", "PHONE"]

# k-anonymity assessment (aggregate data)
from ko_pii.analytics import k_anonymity
report = k_anonymity(records, quasi_keys=["age", "city", "job"], threshold=5)
print(report.k)                     # minimum group size
print(report.satisfies_threshold)   # True/False
print(report.rationale)             # ["준식별자 ['age', 'city', 'job'] 기준 N개 그룹", ...]
```

### Automatic CSV/XLSX table processing

```python
from ko_pii.tabular import anonymize_records
import csv

rows = list(csv.DictReader(open("employees.csv")))
# Headers "성명/주민번호/연락처/주소" → automatically mapped to PERSON/RRN/PHONE/ADDRESS
anon_rows, vault = anonymize_records(rows, strategy="tokenize")
print(anon_rows[0])
# {'성명': '<PERSON_1>', '주민번호': '<RRN_1>', '연락처': '<PHONE_1>', '주소': '<ADDRESS_1>'}
```

### Review-queue workflow (false-positive learning)

Low-confidence detections → saved to a review queue → a user marks them FP/OK/FN → from accumulated markings, dictionary patch suggestions are generated automatically (not applied automatically — applied only after human review).

```python
result = anon.process(text)

# 1. Detections classified as REVIEW due to low confidence (auto-classified per mode)
for record in result.review_items():
    d = record.detection
    print(d.text, d.confidence, d.evidence)

# 2. Save to a separate JSONL queue → user marks verdicts
from ko_pii.review.queue import ReviewQueue
q = ReviewQueue("review.jsonl")
q.enqueue_review_records(result.review_items(), document=text)

# 3. Accumulated markings → generate patch files (common_words candidates / name candidates)
from ko_pii.review.feedback import apply_feedback
apply_feedback(
    queue_path="review.jsonl",
    output_dir="feedback_patches/",
    min_repeat=2,   # same token marked FP 2+ times → candidate (prevents dictionary pollution)
)
# → feedback_patches/common_words_additions.txt  (PERSON FP candidates)
# → feedback_patches/names_to_add.txt           (names marked FN)
# → feedback_patches/summary.json
```

After review, pass `common_words_additions.txt` through `person_exclusions` or
`--person-exclusions-file`; do not patch the installed package dictionary.

### Calling an individual detector

```python
from ko_pii.patterns.rrn import detect

for r in detect("신청인 880101-1234568"):
    print(r.label, r.text, r.confidence, r.legal_basis)
# RRN 880101-1234568 1.0 개인정보보호법 제24조의2
```

---

## 33 PII categories

> List all label keys with `ko-pii --labels` (CLI) or `from ko_pii.labels import ALL_LABELS, LABEL_INFO` (Python).

### Deterministic verification (checksum / whitelist)

| Category | Verification | Risk |
|---|---|---|
| RRN (resident registration number) | 13 digits + date + Korean checksum | CRITICAL |
| FRN (alien registration number) | gender digit 5–8 + checksum | CRITICAL |
| Business registration number | National Tax Service weighted-sum checksum | HIGH |
| Corporate registration number | corporate checksum (RRN takes precedence) | MEDIUM |
| Driver's license number | regional-office code 11–28 whitelist | HIGH |
| Passport number | prefix (M/S/PP/PD etc.) + 8 digits | CRITICAL |
| Credit card | BIN whitelist + Luhn | CRITICAL |
| Parcel number (PNU) | 19 digits + province code | LOW |

### Keyword anchor (both keyword and format required)

| Category | Keywords |
|---|---|
| Health insurance card | 건강보험 / 의료보험 / 보험증 |
| Prescription number | 처방번호 / Rx / 교부번호 |
| Drug code | 약품코드 / KD코드 + Korean GS1 |
| Fax number | 팩스 / FAX |
| Account number | 계좌 / 60+ bank names (3-way anchor) |
| Employee number | 사번 / 공무원번호 / 직원번호 / 임용번호 |
| Civil-petition number | 민원 / 청구 / 정보공개 / 행정심판 |
| Case number | case type (가합 / 고합 / 구합 / 헌가 etc.) |

### Format verification

| Category | Verification |
|---|---|
| Phone number | mobile 010–019 / Seoul 02 / regional 031–064 / VoIP 070 / representative 15xx–18xx / +82 international |
| Email | RFC 5322 |
| IP | IPv4 octets + IPv6 RFC 4291 |
| URL | http(s) / ftp |
| Postal code | province first-digit mapping |
| Vehicle number | new-format NN[가-힣]NNNN + purpose-Hangul whitelist |
| Official document number | ministry name + format |

### Dictionary / heuristic

| Category | Dictionary size |
|---|---|
| Person (PERSON) | 286 surnames + adjacent position + 17 rejection rules |
| Address (ADDRESS) | 17 provinces + 226 districts + 240 frequent dong + 10K legal dong (anchor-conditional) + 38 building suffixes + dong/ho/floor bridge expansion |
| Nationality (NATIONALITY) | 70+ country names (대한민국, 미국, 일본, etc.) |
| Education (EDUCATION) | ~330 universities + abbreviations |
| Major (MAJOR) | ~400 departments (KEDI classification) |
| Position (POSITION) | 250+ titles (government, police, fire, military, prosecutor, judge, private sector) |

### Personal attributes (quasi-identifiers — identification risk when combined)

| Category | Verification | Risk |
|---|---|---|
| Date of birth | date + keyword/full-name/birth-year marker | HIGH |
| Age | "32세 / 32살 / 환갑 / 12개월 아기 / 30대" | INFO |
| Height | "175cm / 1.75m", range 50–250 | INFO |
| Weight | "70kg / 70킬로", range 1–300 | INFO |

> **Quasi-identifier** — not identifying on its own, but carries re-identification risk when combined with other information. `analytics/combined_risk` assesses this automatically.

---

## Detection policy — which prefixes and anchors work

Each PII detection is *not a simple regex match but a multi-gate process*: a combination of **prefix label / keyword anchor / contextual dictionary / format verification**.

### PERSON field labels (50+ items)

1–4 Hangul characters immediately after a label → strong PERSON candidate.

| Domain | Labels |
|---|---|
| Basic | `성명` `이름` `성함` `이 름` |
| Petition / administrative | `신청인` `신청자` `민원인` `청구인` `보호자` `대리인` `당사자` |
| Approval | `기안자` `결재자` `검토자` `보고자` `수신자` `발신자` `참조` |
| Judicial | `원고` `피고` `고소인` `피고소인` `증인` `감정인` |
| Police / fire | `피의자` `피해자` `용의자` `참고인` `신고자` `수사관` `출동대장` |
| HR | `평가자` `피평가자` `면담자` `추천인` |
| Medical | `환자` |

Recognizes 7 label variants: `성명: 홍길동` / `[성명] 홍길동` / `(성명) 홍길동` / `<성명> 홍길동`, etc.

### PERSON rejection rules (17+, FP prevention)

- **Single surname + rank/region/school/bank**: `김부장`, `김포시`, `이화여대` → rejected
- **16 Korean sentence-ending morphemes**: ending in `~은데`, `~는데`, `~라서`, `~까지` → rejected
- **Ministry / institution names**: `보건복지부`, `행정안전부` → rejected
- **Already-pseudonymized notations**: `박씨`, `김모씨`, `○○○ 시민` → rejected

### Detection examples

```
✓ 성명: 김도윤               (field label)
✓ 박지훈 과장님께            (adjacent position)
✓ 홍길동(洪吉童)             (Hanja annotation)
✓ 880101-1234568            (RRN — checksum)
✓ 120-81-47521              (business reg. — NTS checksum)
✓ 4242-4242-4242-4242       (card — Luhn)
✓ M12345678                 (passport)

✗ 김부장이 협조 안 함        (honorific = rejected)
✗ 보건복지부는 검토 후        (ministry name)
✗ 시행일자: 2026-05-20       (non-birthday rejection)
✗ 881301-1000004            (RRN — month 13 invalid)
✗ A12345678                 (passport — A prefix rejected)
```

---

## Processing modes + substitution strategies

| Mode | Blocking threshold | Use |
|---|---|---|
| `PARANOID` | block LOW and above | before external release / sending to an LLM |
| `STRICT` | block MEDIUM and above | practical standard (default) |
| `BALANCED` | block HIGH and above | internal collaboration |
| `PERMISSIVE` | block CRITICAL only | analyst work |
| `AUDIT` | no blocking, detection-only reporting | auditing / statistics |

| Strategy | `880101-1234568` → | Reversible | Description |
|---|---|:-:|---|
| `tokenize` | `<RRN_1>` | ✓ | token substitution, original kept in the Vault |
| `redact` | `[주민등록번호]` | ✗ | replace with the category name |
| `partial` | `880101-1******` | ✗ | mask only part (practical standard) |
| `asterisk` | `**************` | ✗ | asterisk masking |
| `hashed` | `<RRN:abc123>` | ✗ | hash (same value → same token) |
| `fpe` | `771202-2345671` | ✗ | format-preserving encryption (FPE) |

---

## Additional features

| Feature | Description | Install |
|---|---|:---:|
| **HWP/HWPX/DOCX/PDF parser** | Automatic parsing of Hancom Office / MS Word / PDF (body + tables + headers + metadata). See parser details below | `[file]` |
| **Vault encryption** | AES-256-GCM + PBKDF2 with 480k iterations | `[security]` |
| **Audit log (JSONL)** | records `store()`/`reveal()` operations with selectable fail-closed behavior | core |
| **Batch processing** | whole-directory + parallel workers | core |
| **Review queue** | low-confidence detections → human review → automatic learning of FP vocabulary | core |
| **HTML report** | visualization of true positives (green) / false positives (red) / misses (yellow) | core |
| **Hanja/Romanization variants** | `洪吉童` → `홍길동`, `Hong Gildong` → `홍길동` | core |
| **RAG integration** | PII masking of LlamaIndex/LangChain retrieval results (retrieve → mask → LLM) | `[llamaindex]` / `[langchain]` |
| **Rule+ML hybrid** | 4 rule+ML combination modes + threshold-based detection-sensitivity tuning (opt-in) | `[classifier]` |

### Parser details

| Format | Library used | Notes |
|---|---|---|
| HWP 5.x | [olefile](https://pypi.org/project/olefile/) | parses OLE binary records directly, extracts body text |
| HWPX | stdlib (`zipfile` + `xml`) | ZIP+XML structure, no external dependency |
| DOCX | stdlib (`zipfile` + `xml`) | ZIP+XML structure, no external dependency |
| XLSX | stdlib (`zipfile` + `xml`) | sharedStrings + sheet XML |
| PDF | [pdfplumber](https://pypi.org/project/pdfplumber/) (preferred) / [pypdf](https://pypi.org/project/pypdf/) (fallback) | extracts the text layer only (scanned PDFs need OCR) |

> **PDF note:** because PDFs are coordinate-based, spurious spaces and line breaks are commonly inserted per cell. ko-pii automatically corrects unnecessary spaces/line breaks in the middle of PII patterns using its built-in normalization engine (`text_normalizer`). Since pdfplumber performs layout analysis better than pypdf, installing pdfplumber is recommended.

### RAG pipeline integration

Mask PII in retrieved documents before feeding them to the LLM. Within a single retrieval result, the same person is substituted with the same token (`<PERSON_1>`) so context is preserved; pass the `vault` and you can restore via `vault.reveal()` after answer generation.

```python
# LlamaIndex — node postprocessor (retrieve → mask → LLM)
from ko_pii.integrations.llamaindex import KoPiiNodePostprocessor

qe = index.as_query_engine(
    node_postprocessors=[KoPiiNodePostprocessor(mode="STRICT")]
)

# LangChain — drop directly into a Runnable chain
from ko_pii.integrations.langchain import KoPiiRedactor

chain = retriever | KoPiiRedactor(mode="STRICT") | prompt | llm
```

### Rule+ML hybrid (opt-in)

**The core works without ML**, but you can layer ML on top. There are **two distinct hybrids** — they are different features:

| | ① Token-NER hybrid (span replacement) | ② Document-classifier hybrid (confidence blend) |
|---|---|---|
| What | rules = deterministic IDs (checksums), ML = fuzzy categories — **replaces detections** | document-level "has PII" classifier reinforcing rule results (adds no spans) |
| Use | `Anonymizer(secondary_detector=..., merge_mode="role_split")` | `ko_pii.classifier.HybridAnonymizer` |
| Performance | **F1 0.968** on project-built OOD Set A (not independent third-party validation; [`docs/HYBRID_NER.md`](docs/HYBRID_NER.md)) | review triggers / sensitivity tuning |

**① Token-NER hybrid** — plug in an NER model you trained with the [`docs/HYBRID_NER.md`](docs/HYBRID_NER.md) recipe:

```python
from ko_pii import Anonymizer
from ko_pii.integrations.hf_token_ner import HFTokenNERAdapter

ml = HFTokenNERAdapter("out/ner_fuzzy/final")   # model you trained (see recipe)
anon = Anonymizer(secondary_detector=ml, merge_mode="role_split")
result = anon.process(text)   # all strategies (tokenize/partial/redact) and the Vault just work
```

**② Document-classifier hybrid** — via the `[classifier]` extra, configure the combination method and sensitivity yourself:

| Combination mode | Behavior | Use |
|---|---|---|
| `SCORE` | rule detection + classifier-confidence reinforcement | default |
| `GATED` | skip rules if the classifier score < threshold | speed first |
| `REVIEW_FLAG` | if rules find 0 but the classifier is high, "recommend review" | human-review trigger |
| `UNION_BLOCK` | block if either side considers it PII | conservative masking |

Use `classifier_threshold` and `gate_threshold` to **finely tune the rule ↔ ML combination ratio (sensitivity)**.

```python
from ko_pii import Anonymizer, ProcessingMode
from ko_pii.classifier import PIIClassifier, HybridAnonymizer, HybridMode

clf = PIIClassifier.from_pretrained("models/...")
hybrid = HybridAnonymizer(
    Anonymizer(mode=ProcessingMode.BALANCED), clf,
    mode=HybridMode.REVIEW_FLAG,     # combination method
    classifier_threshold=0.5,        # sensitivity (ratio) tuning
)
```

```bash
pip install ko-pii[classifier]      # torch + transformers + scikit-learn
python -m ko_pii.classifier.train ...   # train the model yourself
```

> Pretrained weights are not distributed (training-data licensing) — code and training recipe are provided. **The tuned NER model is planned for a later release** (after licensing review and generalization evaluation).
>
> Hybrid evaluation (rules-only vs hybrid, base vs tuned matrix): [`docs/HYBRID_NER.md`](docs/HYBRID_NER.md) — **+0.14–0.19** over rules-only (klue); the gains are *consistent* only with a *properly tuned Korean NER* (base zero-shot is counterproductive).
> The full experiment trail (training/eval code, run logs, raw results) is archived in (internal NER experiment archive — private).

---

## FAQ

**Q1. Does rules-only, without ML, really work well?**
Korean structural PII can use deterministic format and checksum validation as a
complement to ML. Context-dependent labels such as PERSON may benefit from ML.
The aggregate F1 0.790 on the 540-document administrative/form-like generated
set is reference evidence for domain qualification, not a customer operating
guarantee (see [docs/BENCHMARK.md](docs/BENCHMARK.md) §3b).

**Q2. What if there are too many false positives?**
Use `person_exclusions={...}` or `--person-exclusions-file` for project-scoped
terms, turn PERSON off with `exclude={"PERSON"}`, or adjust the mode. You do not
need to modify the installed package dictionary.

**Q3. Does the Vault enforce access control?**
No. `ReversibleVault` is a storage/restoration primitive and does not authenticate
the caller holding the object or file. Enforce IAM/ACL and key management in the
application, and use encryption plus `--audit-failure-policy raise` for operational
CLI runs. If restoration is unnecessary, use `redact`. See
[`docs/VAULT_SECURITY.md`](docs/VAULT_SECURITY.md).

**Q4. Are HWP tables and headers all captured?**
Yes. With the `[file]` extras installed, body + tables + headers + footers + metadata are all extracted.

**Q5. How does it differ from other tools (Presidio / openai)?**
- **Presidio** — English-centric. Lacks Korea-specific PII (RRN/FRN/passport, etc.)
- **openai/privacy-filter** — general multilingual PII. No labels for Korea's 14 core categories
- **ko-pii** — Korea-specific 33 categories, checksum verification, automatic legal-basis attachment

**Q6. Name-only detection has too many false positives. Can I block only when a name + phone number appear together?**
Use `PERMISSIVE` mode (block CRITICAL only) + conditional reprocessing with `combined_risk`:
```python
result = Anonymizer(mode=ProcessingMode.PERMISSIVE).process(text)
if result.combined_risk.combined_risk >= RiskLevel.HIGH:
    result = Anonymizer(mode=ProcessingMode.STRICT).process(text)
```

---

## Development

```bash
git clone https://github.com/Marker-Inc-Korea/ko-pii
cd ko-pii
pip install -e ".[dev]"
pytest    # full test suite passes
```

Detailed docs: see the [`docs/`](docs/) directory.

---

## License

MIT License

## Legal references

- Personal Information Protection Act (Articles 2, 23, 24, 24-2, 28-2 to 28-5, 29)
- Personal Information Protection Commission, "Guidelines on the Processing of Pseudonymized Information" and "Guidelines on De-identification Measures for Personal Information"
- Commercial Act Article 40, Immigration Act Article 31, National Health Insurance Act Article 96, Act on Real Name Financial Transactions
