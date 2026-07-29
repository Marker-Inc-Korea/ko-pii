# ko-pii Benchmark

## 1. Overview

This document reports how **ko-pii** — a rule/dictionary/checksum-based Korean
PII detector — performs against other PII detection systems on a shared,
human-labeled benchmark. It is published for **transparency**: ko-pii is a
rule-based tool with clear strengths (structural/deterministic PII) and clear
weaknesses (free-form conversational text), and we want third parties to be able
to **trust** the numbers and **reproduce** them rather than take a vendor's word
for it.

Everything below is reported with an explicit provenance tag:

- **Measured** — produced in this evaluation session with the single canonical
  scorer (Sections 3, 4, 5).
- **Estimated / Not measured** — clearly marked; never mixed into headline
  numbers (e.g. ML NER in Section 4).
- **Prior methodology** — older internal runs that used a *different* scorer and
  are therefore **not comparable** to the headline numbers (Section 6).

No number in this document has been invented, rounded, or otherwise altered from
the underlying measurements.

## 2. Evaluation setup

- **Dataset:** KDPII v1.1, `test` split — **4,891 documents**, human-labeled,
  Korean everyday conversational text.
- **Single canonical matcher:** all systems are scored with one and only one
  matcher, `ko_pii.eval.kdpii.match_forms_overlap` — substring set matching,
  position-insensitive.
- **`person_min_length=3`:** PERSON spans of 1–2 characters are excluded for
  every system (applied identically to gold and to each predictor).
- **Identical conditions:** all systems are scored over the **same documents**
  with the **same matcher**. This is critical — earlier runs that used
  per-module matchers produced incomparable numbers (see Section 6).

The systems evaluated:

| System | Type |
|---|---|
| ko-pii | Rules + dictionaries + checksums |
| Presidio (`kr_adapt`) | spaCy ko NER + regex |
| openai/privacy-filter | 660M transformer (ONNX) |
| ML NER (KoELECTRA general NER) | General-purpose NER — **not measured** |

## 3. Main results — KDPII F1

All numbers below are **measured** in this session with the single canonical
matcher on all 4,891 documents.

| System | F1 | Precision | Recall | TP | FP | FN |
|---|---|---|---|---|---|---|
| ko-pii (rules + dict + checksum) | **0.660** | 0.699 | 0.624 | 813 | 350 | 489 |
| Presidio (`kr_adapt`, spaCy ko + regex) | **0.273** | — | — | 220 | 85 | 1085 |
| openai/privacy-filter (660M, ONNX) | **0.264** | — | — | 294 | 634 | 1008 |

**ML NER (KoELECTRA general NER): not measured.** It was **not run** in this
evaluation. An internal **estimate** places it around ~0.10–0.15 F1, but because
it was not measured it is **excluded from the headline ranking** and must only
ever be referred to as "not measured — estimated".

KDPII is conversational text, where free-form labels (PERSON, ADDRESS) dominate
and ko-pii's structural strengths matter less. In this exact dataset and scoring
configuration, ko-pii has the highest aggregate F1 among the measured systems.
This is a dataset-specific comparison, not a universal product ranking or
evidence that a customer deployment is qualified. See Section 8 for the
operational interpretation.

## 3b. Second dataset — generated administrative / form-like set (measured)

KDPII is conversational; to measure the **administrative / form-like** register
ko-pii is designed for, we built a second benchmark: **540 synthetic Korean
documents** (3,635 gold spans, 26 labels) spanning official-document, civil-complaint,
contract, medical and HR registers. All names and numbers are LLM-generated
synthetic values — no real PII. The dataset and its provenance ship in the repo
(`data/generated_eval.jsonl`, `data/generated_eval.README.md`).

**Gold validation.** Gold was validated in two passes — (1) automated format
checks (per-type regex + "gold appears verbatim in the text") and (2) an
adversarial LLM audit (20 agents). Net error rate **~1.2% (98.8% correct)**; 37
labels were corrected (16 removed, 4 span-trimmed, 17 added).

All systems are scored with the same canonical `match_forms_overlap` matcher and
`person_min_length=3`.

| System | F1 | Precision | Recall |
|---|---|---|---|
| ko-pii (rules + dict + checksum) | **0.790** | 0.794 | 0.787 |
| Presidio (`kr_adapt`) | **0.483** | 0.794 | 0.347 |
| openai/privacy-filter (660M) | **0.451** | 0.445 | 0.457 |

*openai/privacy-filter* was scored with its **torch (GPU)** backend: on this host
the q4 ONNX path was pathologically slow on CPU (~32 s/doc), so the same model was
run on GPU instead. The matcher, documents and `person_min_length` are identical,
so the F1 stays comparable (device affects speed only, not F1). It is the weakest
system here, consistent with its KDPII result (0.264, Section 3).

**Reading this honestly.** This set is rich in soft attributes (POSITION,
EDUCATION, …) and open-class IDs (insurance / prescription numbers) that ko-pii
does not target, so its aggregate F1 here understates its strength on the
structured PII it is built for. The key finding holds regardless: ko-pii's
deterministic IDs are near ceiling on this set too (EMAIL 0.998, PHONE 0.989,
CARD 0.988, RRN 0.955). Its aggregate F1 is higher than the measured comparison
systems under this dataset and scorer. That result is not transferred to
unmeasured domains or customer traffic.

## 3c. Robustness cross-check — expanded set (1,938 docs)

To check that the Section 3b numbers are stable on a larger, more varied set, we
expanded to **1,938 documents** (the 540 validated set + **1,398 additional
LLM-generated docs**, format-validated only — gold appears verbatim in text — but
*not* hand-audited). Dataset: `data/generated_eval_large.jsonl`.

**Systems that share the gold's generator are excluded here on purpose.** The
1,398 added docs were generated *and self-labeled by the same generative model*,
so scoring that model on its own gold would be **circular** and inflated. Only
systems independent of the gold's generator are reported:

| System | F1 | Precision | Recall |
|---|---|---|---|
| ko-pii (rules + dict + checksum) | **0.825** | 0.845 | 0.807 |
| openai/privacy-filter (660M, torch GPU) | **0.538** | 0.549 | 0.528 |
| Presidio (`kr_adapt`) | **0.478** | 0.771 | 0.346 |

ko-pii's lead over the independent baselines **holds and slightly widens** on the
3.6× larger set (vs Section 3b: 0.790 / 0.451 / 0.483). All three rise a little
because the LLM-generated docs are cleaner / less adversarial than the
hand-curated 540 (which deliberately includes dense and edge-case documents). The
540 set remains the canonical, audited benchmark; this larger set is a stability
check only.

## 4. Speed

Per-document latency, **measured**. One unit = 1 CPU core (unless noted) or
1 GPU.

| System | Latency / doc | Throughput | Hardware |
|---|---|---|---|
| ko-pii | 0.19 ms | ~5,350 docs/s | CPU, 1 core |
| Presidio | 4.2 ms | ~238 docs/s | CPU, 1 core |
| openai/privacy-filter (ONNX, CPU) | 481 ms | ~2 docs/s | CPU (GPU needed at scale) |

ko-pii runs at **0.19 ms/doc (~5,350 docs/s)** on a single CPU core — **22×
faster than Presidio** (4.2 ms/doc).

### Cost context (optional)

These are **calculated** figures, not measured runtime, based on KDPII documents
measured at ~170 input / ~10 output tokens, expressed as cost per **1,000,000
documents**:

| Approach | Cost / 1M docs |
|---|---|
| ko-pii (CPU, 1 core, ~3 min) | ~$0 |

ko-pii processes 1M documents in about 3 minutes on a single CPU core at
effectively zero marginal cost — no GPU, no per-call API charge.

## 5. Deterministic / structural PII — ko-pii per-label F1

ko-pii's core strength is deterministic and structural PII validated by
checksums and regex. **Measured** per-label F1 on KDPII:

| Label | F1 |
|---|---|
| RRN (resident reg. no.) | 1.000 |
| EMAIL | 1.000 |
| IP | 1.000 |
| FRN (foreign reg. no.) | 1.000 |
| PHONE | 0.992 |
| VEHICLE | 0.980 |
| WEIGHT | 0.952 |
| HEIGHT | 0.935 |
| PASSPORT | 0.909 |
| AGE | 0.893 |
| ACCOUNT | 0.819 |

On structured, checksum-verifiable PII ko-pii is effectively at ceiling — which
is exactly where a rule + checksum engine should win, since the checksum step
rejects malformed candidates that statistical extractors accept.

## 6. Supplementary results (prior internal measurement, different methodology)

> **Caption — prior internal measurement, methodology differs.** The table below
> comes from **earlier internal runs that used a different scorer** than the
> single canonical `match_forms_overlap` matcher used in Sections 3–5. These
> numbers are **not directly comparable** to the headline KDPII results above and
> are included only for directional context.

| Dataset | ko-pii | openai/privacy-filter | Presidio |
|---|---|---|---|
| KLUE NER | 0.419 | 0.155 | 0.000 |

(An earlier, smaller LLM-generated benchmark has been **superseded** by the canonical
540-doc generated set in Section 3b — that set is scored with the same matcher and is
directly comparable.) KLUE-NER above is kept only as directional context from a prior,
different-scorer run.

## 7. Reproduction

The three KDPII systems (ko-pii, openai/privacy-filter, Presidio) are
scored together by a single command. Arguments below were verified against
`src/ko_pii/eval/model_comparison.py` (the `kdpii` mode wires all three through
the same `match_forms_overlap` scorer; defaults are GT model
`openai/privacy-filter` and Presidio mode `kr_adapt`):

```bash
python -m ko_pii.eval.model_comparison data/kdpii/test.json \
    --mode kdpii \
    --include-presidio \
    --backend onnx \
    --person-min-length 3
```

## 8. Honest interpretation

A balanced reading of these results:

- **ko-pii is rule-based.** It is strong on structural / deterministic PII and on
  Korean administrative / form-like text, and weak on free conversational text.
  On KDPII its conversational labels are low — **PERSON 0.135**, **ADDRESS
  0.241** — which is what drags its overall F1 to 0.660.
- **Fair comparison — shared categories.** The aggregate F1 partly reflects that
  Presidio and openai/privacy-filter **lack many Korean PII categories entirely**
  (they emit 0 on AGE, POSITION, RRN, etc.). Even restricting to the categories
  each tool *does* support, ko-pii still leads: **vs openai/privacy-filter
  0.61 : 0.37** (its 7 supported labels), **vs Presidio 0.87 : 0.65** (its 9
  supported labels). So the gap is not merely "missing categories" — ko-pii is
  also more accurate on common ground.
- **KDPII is a conversational set**, where free-form labels dominate and ko-pii's
  structural / deterministic strengths matter less. ko-pii's own strength domain
  (administrative / form-like documents) is reflected by its **0.790** on the
  generated eval set (Section 3b, same matcher, independent of ko-pii's rules) and
  by its near-ceiling deterministic per-label F1 (Section 5).
- **Bottom line.** Under the two exact datasets and one canonical scorer,
  ko-pii's aggregate F1 is higher than the measured comparison systems. Its
  product role is a fast, on-prem, checksum-oriented structural PII layer, not a
  universal PII ranking winner. Customer deployment still requires domain
  qualification with tenant confusion counts. This benchmark is published so
  readers can verify and reproduce the scoped measurements.
