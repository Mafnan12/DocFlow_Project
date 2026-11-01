# Architectural Decision Records (ADRs)

This document formalizes the key engineering and architectural decisions governing DocFlow.

---

## ADR-001: Two Independent Extraction Approaches (Approach A & Approach B)

- **Status:** Accepted
- **Context:** Extracting structured JSON from unstructured invoices and noisy receipt images with a single prompt provides no intrinsic verification signal. If a single model misreads a blurry digit (e.g. `8` as `3`), the system has no cross-check.
- **Options Considered:**
  1. *Single Vision LLM:* Fast and simple, but has no independent OCR verification and prone to subtle misreadings on dense tables.
  2. *Single OCR + Text LLM:* Cheap, but loses 2D spatial layout cues and fails when OCR groups text incorrectly.
  3. *Dual Independent Approaches:* Run Approach A (OCR + Text LLM) and Approach B (Direct Vision Multimodal LLM) in parallel, comparing outputs.
- **Decision:** Option 3. Implement two independent extraction pipelines that feed into an ensemble reconciler.
- **Consequences:** Provides an objective inter-model agreement signal ($S_{\text{agreement}}$) for field confidence scoring. When both agree, confidence is high; when they disagree, the system can investigate or flag for human review. Costs two LLM calls per document, which is accommodated within free-tier quotas through caching.

---

## ADR-002: Canonical String Output from LLMs with Deterministic `Decimal` Parsing

- **Status:** Accepted
- **Context:** Financial amounts must be exact. Standard IEEE 754 floating-point types (`float` in Python/JavaScript) introduce rounding artifacts (e.g., `0.1 + 0.2 = 0.30000000000000004`), which cause arithmetic validations to fail incorrectly. Furthermore, international documents vary widely in format (e.g. European `1.250,50` vs US `1,250.50`).
- **Options Considered:**
  1. *Prompt LLMs to output raw floats:* Leads to precision loss and validation failures.
  2. *Prompt LLMs to output formatted currency strings and parse in prompt:* LLMs frequently hallucinate format conversions.
  3. *Canonical string output + deterministic Python parsing:* LLMs output canonical strings (`"1250.50"`); deterministic, unit-tested Python functions parse them into `Decimal` and standardized `date` objects.
- **Decision:** Option 3.
- **Consequences:** Eliminates float rounding bugs, guarantees locale-aware parsing is reproducible and unit-testable, and isolates normalization errors into traceable `parse_errors` arrays.

---

## ADR-003: Deterministic Code Validation Engine Instead of LLM Verification

- **Status:** Accepted
- **Context:** We need to verify whether line item subtotals, tax calculations, discounts, and grand totals are mathematically consistent.
- **Options Considered:**
  1. *Ask an LLM "Does this invoice add up?":* Subjective, prone to hallucination, non-deterministic, and cannot provide mathematical guarantees.
  2. *Deterministic Rule Engine (Python):* Check 13 explicit rules (V01–V13) with strict mathematical formulas and configurable tolerance thresholds.
- **Decision:** Option 2.
- **Consequences:** Arithmetic correctness is 100% deterministic, explainable, and provable. When a rule fails, the exact discrepancy ($\text{expected} - \text{actual}$) is calculated and fed to either the self-correction agent or the human review UI.

---

## ADR-004: Self-Correction via Targeted Crops and an Anti-Gaming OCR-Support Gate

- **Status:** Accepted
- **Context:** When extracted data fails arithmetic validation, we want the system to autonomously attempt a repair without inventing numbers to "make the math work".
- **Options Considered:**
  1. *Generic Retry:* Re-send the whole image and prompt saying "Please try again." (Ineffective; repeats same errors).
  2. *Feedback-only Retry:* Send validation errors back to the model with the full image. (Prone to "gaming" — the model alters numbers arbitrarily to force arithmetic to balance).
  3. *Targeted Crops + OCR-Support Gate:* Crop only the suspect region (e.g. line items or tax block) at 2x zoom, run localized re-OCR, and accept a correction **only** if arithmetic violations decrease AND the proposed numbers physically exist in the crop's OCR text.
- **Decision:** Option 3.
- **Consequences:** Zoomed crops resolve small-print legibility issues. The OCR-support gate strictly prevents the model from hallucinating numbers to pass tests. Corrections that fail the gate are demoted to human review suggestions.

---

## ADR-005: Field-Level Confidence Scoring from Interpretable Signals

- **Status:** Accepted
- **Context:** Bookkeepers must understand *why* a document was auto-approved or flagged. Black-box confidence scores (e.g. LLM token logprobs) are uninterpretable and vary drastically between model providers.
- **Options Considered:**
  1. *Average LLM Log-Probabilities:* Inconsistent across providers (Groq vs Gemini vs OpenAI), difficult to calibrate.
  2. *Rule-based Heuristic:* Arbitrary binary flags.
  3. *Weighted Interpretable Signals:* Combine 4 distinct, interpretable signals: Model Agreement (45%), Validation Rule Status (35%), OCR Text Support (10%), and Self-Correction Stability (10%).
- **Decision:** Option 3. Thresholds and weights are calibrated exclusively on the `dev` dataset split.
- **Consequences:** Human reviewers can immediately see *which* signal triggered a flag (e.g., "Tax flagged: Approach A and B disagree"). Guarantees auditability.

---

## ADR-006: Routing Optimized for Auto-Approval Precision Over Automation Rate

- **Status:** Accepted
- **Context:** In enterprise data entry, what trade-off should routing optimize?
- **Options Considered:**
  1. *Maximize Auto-Approval Rate:* Push automation to 95%, accepting that 2–5% of auto-approved invoices will contain undetected errors.
  2. *Maximize Auto-Approval Precision:* Tune confidence thresholds so that auto-approved documents achieve $\ge 98\%$ precision, routing any ambiguous document to human review.
- **Decision:** Option 2.
- **Consequences:** Aligns with commercial accounting realities: human review of 20% of documents costs far less than forensic audits and amended tax filings caused by silent automated errors.

---

## ADR-007: PostgreSQL Queue with `FOR UPDATE SKIP LOCKED` Instead of Redis/Celery

- **Status:** Accepted
- **Context:** Background processing requires a queue to manage worker jobs, retries, and document ingestion states.
- **Options Considered:**
  1. *Celery + Redis:* Traditional setup, but introduces two extra infrastructure services, separate broker state, and hosting cost/complexity.
  2. *PostgreSQL `FOR UPDATE SKIP LOCKED`:* Implement the job queue directly in PostgreSQL using transactional row-level locks.
- **Decision:** Option 2.
- **Consequences:** Zero extra services to deploy or monitor ($0 budget compliance). Atomic transactional consistency between job status, document metadata, and extraction records. Safe concurrent workers with no race conditions or double-processing.

---

## ADR-008: PDF Text Layer Detection with OCR Bypass

- **Status:** Accepted
- **Context:** Digital invoices (e.g., generated by Stripe, AWS, QuickBooks) already contain embedded text layers. Running full OCR on digital PDFs is slow, computationally wasteful, and can introduce OCR spelling typos.
- **Options Considered:**
  1. *Always OCR everything:* Uniform pipeline, but slow and error-prone on digital vector PDFs.
  2. *Inspect Text Layer with `pypdfium2`:* If a digital PDF contains $\ge 50$ clean characters per page, extract the text stream directly for Approach A; reserve rasterization and OCR for scanned documents.
- **Decision:** Option 2.
- **Consequences:** Digital invoices process in under 3 seconds with 100% character accuracy, drastically reducing CPU usage on free-tier deployments.

---

## ADR-009: Fail-Safe Document Routing (Zero Lost Documents)

- **Status:** Accepted
- **Context:** Real-world documents may be corrupt, unreadable, or cause unhandled exceptions during processing.
- **Options Considered:**
  1. *Drop failing jobs or mark as fatal error:* Leaves documents in limbo; bookkeepers lose track of client expenses.
  2. *Route all unrecoverable failures to Review Queue with Diagnostic Flags:* Any document that exhausts worker retries automatically transitions to `needs_review` with an attached error trace.
- **Decision:** Option 2.
- **Consequences:** Guarantees zero dropped documents. Bookkeepers can view the failed file, read the diagnostic reason, and manually enter or re-upload the document.

---

## ADR-010: Dataset Evaluation Masks for Fair Metric Reporting

- **Status:** Accepted
- **Context:** Public benchmark datasets annotate different subsets of fields. SROIE receipts do not label line items or tax breakdowns; CORD receipts often do not annotate vendor names or dates.
- **Options Considered:**
  1. *Score all fields against empty defaults:* Heavily penalizes models for predicting unannotated real fields (e.g. SROIE line items).
  2. *Dynamic Evaluation Masks:* Each dataset defines a `labeled_fields` mask. The scoring engine evaluates accuracy only against annotated fields.
- **Decision:** Option 2.
- **Consequences:** Prevents skewed evaluation metrics and allows honest comparisons across heterogeneous benchmarks.

---

## ADR-011: Multi-Level Extraction Caching

- **Status:** Accepted
- **Context:** Evaluating models over hundreds of test documents requires thousands of LLM API calls, quickly exhausting free-tier rate limits and daily quotas.
- **Options Considered:**
  1. *Live calls for every experiment:* Hits rate limits rapidly; impossible to iterate on validation rules or confidence thresholds.
  2. *Deterministic Response Caching:* Cache extraction outputs on disk keyed by `SHA256(document_hash + approach + prompt_version + model_id)`.
- **Decision:** Option 2.
- **Consequences:** Running confidence threshold sweeps, ablation experiments, and error analyses becomes instantaneous and costs 0 API calls once the base extractions are recorded.
