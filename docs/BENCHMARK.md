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
- **Identical conditions:** all 5 systems are scored over the **same documents**
  with the **same matcher**. This is critical — earlier runs that used
  per-module matchers produced incomparable numbers (see Section 6).

The five systems evaluated:

| System | Type |
|---|---|
| Gemma-4-31B-it | Self-hosted LLM (vLLM, prompt-based extraction) |
| ko-pii | Rules + dictionaries + checksums |
| Presidio (`kr_adapt`) | spaCy ko NER + regex |
| openai/privacy-filter | 660M transformer (ONNX) |
| ML NER (KoELECTRA general NER) | General-purpose NER — **not measured** |

## 3. Main results — KDPII F1

All numbers below are **measured** in this session with the single canonical
matcher on all 4,891 documents.

| System | F1 | Precision | Recall | TP | FP | FN |
|---|---|---|---|---|---|---|
| Gemma-4-31B-it (self-hosted LLM) | **0.796** | 0.850 | 0.748 | 958 | 169 | 323 |
| ko-pii (rules + dict + checksum) | **0.660** | 0.699 | 0.624 | 813 | 350 | 489 |
| Gemma-4-E4B-it (smallest Gemma 4, ~4B) | **0.613** | 0.659 | 0.572 | 739 | 383 | 552 |
| Presidio (`kr_adapt`, spaCy ko + regex) | **0.273** | — | — | 220 | 85 | 1085 |
| openai/privacy-filter (660M, ONNX) | **0.264** | — | — | 294 | 634 | 1008 |

**ML NER (KoELECTRA general NER): not measured.** It was **not run** in this
evaluation. An internal **estimate** places it around ~0.10–0.15 F1, but because
it was not measured it is **excluded from the headline ranking** and must only
ever be referred to as "not measured — estimated".

KDPII is conversational text, which favors LLMs. The large Gemma-4-31B leads;
ko-pii is second. Note the **size effect**: the **smallest Gemma-4 (E4B) scores
0.613 — *below* ko-pii's 0.660** — so on conversational Korean only the large 31B
model beats the rules, while the small LLM does not. (On the administrative
generated set in Section 3b the order flips: E4B 0.882 > ko-pii 0.784.) See
Section 8 for an honest interpretation.

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
| Gemma-4-31B-it (self-hosted LLM) | **0.964** | 0.963 | 0.966 |
| Gemma-4-E4B-it (smallest Gemma 4, ~4B) | **0.882** | 0.925 | 0.843 |
| ko-pii (rules + dict + checksum) | **0.784** | 0.792 | 0.776 |
| Presidio (`kr_adapt`) | **0.483** | 0.794 | 0.347 |
| openai/privacy-filter (660M) | **0.451** | 0.445 | 0.457 |

*openai/privacy-filter* was scored with its **torch (GPU)** backend: on this host
the q4 ONNX path was pathologically slow on CPU (~32 s/doc), so the same model was
run on GPU instead. The matcher, documents and `person_min_length` are identical,
so the F1 stays comparable (device affects speed only, not F1). It is the weakest
system here, consistent with its KDPII result (0.264, Section 3).

**Reading this honestly.** Two factors inflate the LLM lead on this set:
(1) the gold is LLM-authored and LLM-labeled, so its label conventions — especially
for soft attributes (POSITION, EDUCATION, …) — align with what an LLM extracts;
(2) the set is rich in those soft attributes and in open-class IDs
(insurance / prescription numbers) that ko-pii does not target. The independent
human-labeled KDPII gap (0.796 vs 0.660) is the more realistic LLM-vs-rules
comparison. Two findings still hold regardless: ko-pii's deterministic IDs are
near ceiling here too (EMAIL 0.998, PHONE 0.989, CARD 0.988, RRN 0.955), and the
**smallest Gemma 4 (E4B, ~4B) reaches 91 % of the 31B model's F1** at ~8× smaller
size — though any LLM still carries the GPU / cost / non-determinism that a rule
engine does not.

## 4. Speed

Per-document latency, **measured**. One unit = 1 CPU core (unless noted) or
1 GPU.

| System | Latency / doc | Throughput | Hardware |
|---|---|---|---|
| ko-pii | 0.19 ms | ~5,350 docs/s | CPU, 1 core |
| Presidio | 4.2 ms | ~238 docs/s | CPU, 1 core |
| openai/privacy-filter (ONNX, CPU) | 481 ms | ~2 docs/s | CPU (GPU needed at scale) |
| Gemma-4-31B (vLLM, concurrency 16) | median 0.30 s / mean 0.58 s | 27.6 docs/s | 1 GPU |

ko-pii is roughly **~200×** faster than the self-hosted LLM per document.

### Cost context (optional)

These are **calculated** figures, not measured runtime, based on KDPII documents
measured at ~170 input / ~10 output tokens, expressed as cost per **1,000,000
documents**:

| Approach | Cost / 1M docs |
|---|---|
| ko-pii (CPU, 1 core, ~3 min) | ~$0 |
| Gemini 2.0 Flash | ~$23 |
| GPT-4o-mini | ~$35 |
| Claude 3.5 Haiku | ~$196 |
| GPT-4o | ~$575 |

Self-hosted Gemma is ~1 GPU for ~10 hours per 1M documents (compute, not API
cost).

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
is exactly where a rule + checksum engine should win and where LLMs cannot offer
checksum validation.

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

The three non-LLM KDPII systems (ko-pii, openai/privacy-filter, Presidio) are
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

Gemma is scored separately: prompts are sent to a self-hosted vLLM
OpenAI-compatible endpoint, and the extracted PII is scored with the **same**
`match_forms_overlap` matcher and the same `person_min_length=3` so that its F1
is directly comparable to the table in Section 3.

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
- **The LLM (Gemma) wins on conversational F1** (0.796 vs 0.660), but it is
  **~200× slower** per document. API-hosted LLMs additionally **send PII to an
  external service** and **cannot perform checksum validation**, so they produce
  false positives that a checksum-backed rule engine rejects.
- **KDPII is a conversational set, which structurally favors LLMs.** ko-pii's own
  strength domain (administrative / form-like documents) is reflected by its
  **0.784** on the generated eval set (Section 3b, same matcher, independent of
  ko-pii's rules) and by its near-ceiling deterministic per-label F1 (Section 5).
- **Bottom line.** If your priority is conversational free-text recall and you
  can pay the cost and latency, the LLM is better on this set. If your priority
  is **cost (≈$0), speed (~5,350 docs/s on one CPU core), fully on-prem
  operation with no external PII transmission, and checksum-verified
  deterministic PII**, ko-pii is the stronger choice. The two tools occupy
  different operating points; this benchmark is published so readers can pick the
  right one for their constraints.
