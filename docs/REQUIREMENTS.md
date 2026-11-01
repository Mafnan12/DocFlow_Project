# DocFlow Requirements Specification

## 1. Client Brief: LedgerLite Bookkeeping

> **Client:** LedgerLite Bookkeeping (fictional), an accounting firm managing expense processing and accounts payable for dozens of small-business clients.
>
> **The Problem:**
> Staff bookkeepers manually re-type financial data from thousands of receipts and invoices every month: vendor names, invoice dates, line item quantities, unit prices, tax amounts, and totals.
>
> The process is:
> - **Costly & Slow:** Hundreds of billable hours spent on tedious data entry.
> - **Error-Prone:** Typos in line items or tax rates propagate into clients' general ledgers, requiring painful reconciliations during audits.
> - **High Variance:** Clients submit documents via phone snapshots, flatbed scans, and digital PDFs with vastly different layouts, orientations, image quality, and international currencies.
>
> **The Objective:**
> Build an autonomous, multimodal processing system that ingests receipts and invoices, validates its own extractions through deterministic arithmetic, self-corrects ambiguous regions, auto-approves confident extractions, and routes uncertain records to human reviewers with suspect fields pre-highlighted.

---

## 2. Quantitative Targets & Success Criteria

### 2.1 The Core Business Metric: Auto-Approval Precision vs. Review Rate
Standard document AI systems boast average accuracy (e.g., "95% accuracy"). In enterprise bookkeeping, this is unacceptable: 500 silently corrupted invoices in a batch of 10,000 documents destroy ledger integrity.

LedgerLite prioritizes **Auto-Approval Precision over Raw Automation Rate**:

$$\text{Auto-Approval Precision} = \frac{\text{Correct Auto-Approved Documents}}{\text{Total Auto-Approved Documents}}$$

| Metric | Target | Rationale |
|---|---|---|
| **Auto-Approval Precision** | **$\ge 98.0\%$** on test split | Unchecked errors entering accounting systems must be near zero. |
| **Review Rate** | **$\le 25.0\%$** at $\ge 98\%$ precision | At least 75% of documents should be processed without human touch. |
| **Field-Level F1 (Critical Fields)** | **$\ge 95.0\%$** | High extraction fidelity on `vendor_name`, `date`, `currency`, and `total`. |
| **Arithmetic Consistency** | **$100.0\%$** for auto-approvals | Zero mathematical contradictions allowed on auto-approved files. |

### 2.2 Operational & Efficiency Targets

| Requirement | Target | Strategy |
|---|---|---|
| **Operating Cost** | **$0.00** ongoing API cost | Leverage zero-cost LLM tiers (Groq, Gemini, GitHub Models) and local OCR models. |
| **Processing Latency (p50)** | $< 12$ seconds per document | Asynchronous background processing queue with PDF text-layer bypass. |
| **Processing Latency (p95)** | $< 35$ seconds per document | Bounded self-correction agent loops (max 2 rounds). |
| **Reliability** | Zero document drop | Transient provider failures retry; permanent errors route to human review. |
| **Auditability** | 100% immutable history | Every extraction, correction, and approval recorded with user ID and timestamp. |

---

## 3. Users, Roles, and Tenant Scoping

### 3.1 User Roles

| Role | Permissions & Responsibilities |
|---|---|
| **`bookkeeper`** | - Upload documents (PDF, JPG, PNG) assigned to specific LedgerLite clients.<br>- Monitor processing queue status.<br>- Review flagged/uncertain documents with suspect fields highlighted.<br>- Correct erroneous fields with instant arithmetic re-check.<br>- Approve validated documents and trigger CSV export. |
| **`admin`** | - All `bookkeeper` permissions.<br>- Access system analytics dashboard (review rate, error breakdowns, latency).<br>- View active routing thresholds and signal weights.<br>- Execute demo database reset. |

### 3.2 Client Tenant Scoping
Documents and exports are strictly isolated by LedgerLite client entities:
- **`kopi-corner`**: Kopi Corner Café (retail food/beverage receipts, Southeast Asian currency notes).
- **`brightline`**: Brightline Studio (creative agency, digital multi-line service invoices).
- **`metro-hardware`**: Metro Hardware (inventory supplier receipts with dense item lists).

---

## 4. Scope Boundaries

### In Scope
1. **Multimodal Ingestion:** JPG, PNG, and PDF support up to 10MB and 3 pages per file.
2. **Document Classification:** Distinguish receipts, invoices, and unsupported "other" documents.
3. **Dual Extraction Pipeline:** Independent Approach A (OCR + Text LLM) and Approach B (Direct Vision Multimodal LLM).
4. **Deterministic Validation:** 13 strict arithmetic rules (V01–V13) executing in Python using `Decimal`.
5. **Ensemble Reconciliation:** Merge extractions from both approaches with field provenance tracking.
6. **Agentic Self-Correction:** Targeted crop generation, re-OCR, and an OCR-support anti-gaming gate.
7. **Calibrated Confidence Scoring:** Field-level confidence scores based on model agreement, validation outcomes, and OCR token support.
8. **Human Review Interface:** Streamlit UI displaying side-by-side document views with flagged field highlighting.
9. **Export Service:** Client-scoped CSV exports (and optional Google Sheets sync).
10. **Enterprise Queue:** Asynchronous PostgreSQL worker queue utilizing `FOR UPDATE SKIP LOCKED`.

### Out of Scope
1. Handwritten receipts (system assumes printed receipts/invoices).
2. Multi-invoice composite PDFs (limitation: one document entity per uploaded file).
3. Direct OAuth integration with commercial ERPs (Xero/QuickBooks) — exports provided via standard structured CSV.
4. Paid proprietary OCR/LLM APIs.
