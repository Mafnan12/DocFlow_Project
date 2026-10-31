# DocFlow Requirements and Client Brief

## 1. Client Brief: LedgerLite Bookkeeping

> **Client:** LedgerLite Bookkeeping (fictional), a bookkeeping firm managing expenses for dozens of small-business clients.
>
> **Problem:** Staff manually type data from thousands of receipts and invoices every month: vendor, date, line items, taxes, totals. It is slow, tedious, and error-prone. Clients send documents as phone photos, scans, and PDFs, in different layouts and currencies.
>
> **Request:** A system that:
> 1. Accepts receipts and invoices (images and PDFs) for each of LedgerLite's clients.
> 2. Extracts vendor, date, currency, line items, subtotal, tax, discounts, service charges, and total.
> 3. Checks its own work (do the numbers add up?) and fixes its own mistakes when it can.
> 4. **Auto-approves only documents it is confident about**, and sends the rest to staff for review, with uncertain fields highlighted.
> 5. Lets staff correct fields quickly, and remembers corrections.
> 6. Exports clean data per client to CSV or spreadsheets.

## 2. Core Business Metric

**Auto-approval precision at an acceptable review rate.**

LedgerLite prioritizes zero silent errors over 100% automation. In bookkeeping, silent errors corrupt general ledgers; the system must provide provable reliability. High precision on auto-approved files takes precedence over raw average accuracy.

## 3. Users and Roles

| Role | Capabilities |
|---|---|
| `bookkeeper` | Upload documents for a client, view processing status, review and correct flagged documents, approve, export |
| `admin` | Everything above + metrics dashboard, threshold settings view, demo reset |

## 4. Scope

- **In scope:** Upload (JPG, PNG, PDF), preprocessing, document classification (receipt / invoice / other), dual extraction approaches (Approach A: OCR + text LLM; Approach B: vision LLM), normalization, deterministic validation (rules V01–V13), reconciliation, self-correction agent with targeted crop/re-OCR, confidence scoring, routing, review UI with corrections, CSV export (Google Sheets optional), job queue and worker (`SKIP LOCKED`), evaluation suite, tracing, deployment, CI.
- **Out of scope:** Handwritten documents, email ingestion, accounting software direct integration, multi-document PDFs (one document per file).

## 5. Non-Functional Requirements

- **Cost:** Strictly $0 operating cost (free tiers and local open-source models).
- **Correctness:** Money amounts handled via Python `Decimal`. Validation is deterministic code, not LLM opinion.
- **Auditability:** Every extraction, correction, and approval recorded with timestamps and user IDs.
- **Reproducibility:** Evaluation reports record dataset split, configuration, prompt versions, models, and git commit.
