# DocFlow Operations and Handover Guide

This manual covers deployment, operations, maintenance, and production considerations for DocFlow.

## 1. Quickstart (Local Development)

```bash
# 1. Environment and dependencies
cp .env.example .env
uv sync --all-extras

# 2. Database
docker compose up -d postgres
uv run alembic upgrade head

# 3. Running Services
# Terminal 1: FastAPI Server
uv run uvicorn docflow.api.main:app --reload --port 8000

# Terminal 2: Background Worker
uv run python -m docflow.queue.worker

# Terminal 3: Streamlit UI
uv run streamlit run ui/Home.py --server.port 8501
```

## 2. Background Worker Architecture

The worker polls the `documents` / `jobs` table using PostgreSQL `FOR UPDATE SKIP LOCKED`.
- **Concurrency:** Safe for multiple concurrent worker instances without duplicate processing or race conditions.
- **Failures:** Transient errors are retried with exponential backoff (up to 3 attempts). Permanent errors update status to `failed_review` so no document is silently lost.
- **Stale Job Recovery:** Jobs locked in `processing` state for longer than 15 minutes without step updates are automatically re-queued.

## 3. Synthetic Benchmark Data

T05 generates reproducible invoices locally with Faker, Jinja2, and ReportLab. ReportLab is used instead of WeasyPrint so Windows development does not require GTK. Ground truth is created from the source data model before rendering and is written as canonical JSONL.

```bash
# Generate PDFs, inspection HTML, rasterized PNGs, and exact ground truth
uv run python scripts/generate_invoices.py --count 500 --seed 42

# Apply camera/scan degradations to half of the generated images
uv run python scripts/degrade_images.py --fraction 0.5 --seed 42
```

Outputs are written under `data/synthetic/` and `data/ground_truth/` (both are intentionally git-ignored). The degradation manifest records the operation names and sampled parameters for each image.

## 4. Threshold Calibration Runbook

To modify routing thresholds safely:
1. Never modify thresholds directly based on test results.
2. Run `uv run python evals/threshold_sweep.py --split dev`.
3. Inspect the Precision vs. Review Rate curve.
4. Select the threshold meeting LedgerLite's required precision target (e.g. 99%).
5. Update `config/confidence.yaml` with the chosen threshold and commit the sweep report.
