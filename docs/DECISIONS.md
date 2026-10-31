# Architectural Decision Records (ADRs)

This document records the foundational architectural decisions made for DocFlow.

---

### ADR-001: Two independent extraction approaches
- **Decision:** Implement both Approach A (OCR + Text LLM) and Approach B (Multimodal Vision LLM) running independently.
- **Reason:** Enables objective agreement measurement between two fundamentally different extraction paradigms, providing a strong signal for field confidence.

### ADR-002: Canonical strings from LLM, deterministic parsing to `Decimal` and dates
- **Decision:** LLMs output standardized string representations of numbers; deterministic Python code parses them into `Decimal` and standardized dates.
- **Reason:** Eliminates floating-point inaccuracies, enables testable locale normalization (e.g. European commas vs. dots), and ensures exact arithmetic.

### ADR-003: Validation is deterministic code, not LLM judgment
- **Decision:** All arithmetic consistency (V01–V13) is checked strictly in Python rules using `Decimal`.
- **Reason:** Arithmetic must be 100% predictable, explainable, and provable. LLMs are prone to hallucinating arithmetic correctness.

### ADR-004: Self-correction uses specific feedback, targeted crops, and an OCR-support gate
- **Decision:** When validation fails, the agent targets specific failing regions with zoomed crops and re-OCR. A proposed correction is only accepted if it satisfies arithmetic AND the new numbers are confirmed in the localized crop OCR text.
- **Reason:** Prevents the LLM from inventing fake totals just to satisfy arithmetic checks.

### ADR-005: Field-level confidence from interpretable signals; thresholds tuned on dev split only
- **Decision:** Compute field confidence using a weighted sum of interpretable signals (model agreement, validation pass status, OCR token support, correction history).
- **Reason:** Transparent to human reviewers and prevents data leakage by never tuning thresholds on the test split.

### ADR-006: Routing optimizes auto-approval precision, not average accuracy
- **Decision:** Routing thresholds prioritize maximizing precision of auto-approved documents over raw throughput.
- **Reason:** Matches the core business requirement of LedgerLite: human review of ambiguous docs is far cheaper than correcting silent errors in accounting books.

### ADR-007: Postgres job queue with `SKIP LOCKED` instead of Redis/Celery
- **Decision:** Implement job queue and status tracking directly in Postgres using `FOR UPDATE SKIP LOCKED`.
- **Reason:** Zero additional services required, safe concurrent workers, transactional state consistency, and native row locking.

### ADR-008: Use PDF text layer when present; OCR only when needed
- **Decision:** Detect digital PDF text layers using `pypdfium2`. If sufficient text layer exists, bypass heavy OCR for Approach A.
- **Reason:** Faster execution, lower CPU usage, and 100% character fidelity for digital-native invoices.

### ADR-009: Failed processing goes to review, never silently dropped
- **Decision:** Any unrecoverable extraction or processing failure routes the document into the human review queue with failure diagnostics.
- **Reason:** Guarantees zero document loss in production bookkeeping.

### ADR-010: Per-dataset evaluation masks
- **Decision:** Evaluate accuracy only on the specific fields ground-truthed by each dataset (e.g., SROIE lacks line items; CORD lacks vendor names).
- **Reason:** Prevents penalizing models for missing ground truth that the source dataset does not annotate.

### ADR-011: Cache extraction outputs by `(doc_hash, approach, prompt_version, model)`
- **Decision:** Persist raw LLM responses hashed by document content, prompt version, and model parameters.
- **Reason:** Enables rapid threshold sweeps, ablation studies, and iterative development without hitting free-tier rate limits or wasting LLM quotas.
