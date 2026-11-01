# Datasets and Ground Truth Documentation

DocFlow benchmarks performance across public receipt datasets and synthetic invoice generators with mathematically verified ground truth.

---

## 1. Public Benchmark Datasets

### 1.1 CORD v2 (Consolidated Receipt Dataset for Post-OCR Parsing)
- **Source:** Hugging Face [`naver-clova-ix/cord-v2`](https://huggingface.co/datasets/naver-clova-ix/cord-v2)
- **Origin:** Naver Clova Research
- **Domain:** Mobile camera photos of retail and restaurant receipts from Indonesia.
- **Annotated Fields:**
  - `line_items`: Item description, quantity, unit price, item total.
  - `subtotal`, `tax`, `service_charge`, `discount`, `total`.
- **Domain Nuances:**
  - **Currency:** Indonesian Rupiah (IDR).
  - **Number Formatting:** Thousands separators frequently use periods (e.g., `60.000` means `60,000`).
  - **Zero Decimals:** IDR transactions do not use fractional cents/cents decimals.
- **License:** Creative Commons Attribution 4.0 International ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
- **Evaluation Mask:** `["line_items", "subtotal", "tax", "service_charge", "discount", "total"]`. (Vendor name and date are masked during official benchmark scoring due to incomplete annotations in the source labels).

### 1.2 SROIE (ICDAR 2019 Scanned Receipts Information Extraction)
- **Source:** ICDAR 2019 Robust Reading Competition / Hugging Face mirrors
- **Origin:** Malaysian commercial receipts
- **Domain:** Flatbed scans of grocery, dining, and utility receipts.
- **Annotated Fields:**
  - `company` $\rightarrow$ mapped to `vendor_name`
  - `date` $\rightarrow$ normalized ISO `YYYY-MM-DD`
  - `address` $\rightarrow$ mapped to `vendor_address`
  - `total` $\rightarrow$ grand total amount
- **Domain Nuances:**
  - **Currency:** Malaysian Ringgit (MYR).
  - **Date Formats:** Mixed formats (e.g. `DD/MM/YYYY`, `DD-MMM-YY`, `YYYY-MM-DD`).
  - **Rounding Adjustments:** Malaysian cash rounding laws (nearest 5 cents) create minor discrepancies between item totals and grand totals.
- **License:** Research and academic evaluation use per ICDAR 2019 competition terms.
- **Evaluation Mask:** `["vendor_name", "date", "total"]`. (Line items are masked because the raw competition dataset does not provide bounding-box level item annotations).

---

## 2. Synthetic Invoices & Degradation Suite

### 2.1 Synthetic Invoices Generator
To test multi-line business invoices across diverse global layouts and currencies (which public receipt datasets lack), DocFlow includes a synthetic generator (`scripts/generate_invoices.py`):
- **Engine:** Jinja2 HTML templates rendered to PDF via WeasyPrint / ReportLab.
- **Data Generator:** `Faker` with fixed random seed.
- **Coverage:** 4 distinct visual layouts (modern minimal, corporate classic, dual-column service, compact retail).
- **Currencies Covered:** USD (`$`), EUR (`€`), GBP (`£`), PKR (`Rs`), AED (`AED`).
- **Ground Truth:** 100% complete ground truth generated directly from source data models with exact `Decimal` precision.

### 2.2 OpenCV Degradation Pipeline (`scripts/degrade_images.py`)
To benchmark robustness against real-world mobile capture flaws, synthetic invoices undergo realistic programmatic degradations:
- **Perspective Distortion & Skew:** Simulating angled desk snapshots ($[-5^\circ, +5^\circ]$).
- **Gaussian & Motion Blur:** Simulating hand shake ($k_{\text{size}} \in [3, 7]$).
- **Photometric Noise:** Gaussian sensor noise and uneven lighting gradients.
- **Low Contrast / Faded Ink:** Simulating thermal printer fading.

---

## 3. Unified Ground-Truth Schema

All datasets are converted into a standardized JSON schema by `scripts/convert_ground_truth.py`:

```json
{
  "doc_id": "cord_test_0042",
  "source": "cord",
  "file": "data/cord/test/0042.png",
  "doc_type": "receipt",
  "labeled_fields": [
    "line_items",
    "subtotal",
    "tax",
    "service_charge",
    "discount",
    "total"
  ],
  "ground_truth": {
    "vendor_name": null,
    "vendor_address": null,
    "invoice_number": null,
    "date": null,
    "currency": "IDR",
    "line_items": [
      {
        "description": "ES KOPI SUSU",
        "quantity": "2",
        "unit_price": "18000.00",
        "total": "36000.00"
      }
    ],
    "subtotal": "36000.00",
    "tax": "3600.00",
    "service_charge": "0.00",
    "discount": "0.00",
    "rounding": "0.00",
    "total": "39600.00"
  }
}
```

---

## 4. Dataset Splits & Anti-Leakage Protocol

- **Dev Split:** Used strictly for prompt engineering, threshold calibration sweeps, and error analysis.
- **Test Split:** Sealed and held out until final benchmark generation. Never inspect, debug, or tune thresholds on the test split.
- **Fixed Random Seed:** `SEED = 42` is enforced across all data splitters and synthetic generators to guarantee exact reproducibility across all machines.

---

## 5. Download Sources & Versions

### 5.1 CORD v2

| Field | Value |
|---|---|
| **HuggingFace ID** | `naver-clova-ix/cord-v2` |
| **Download method** | `datasets` library (`load_dataset("naver-clova-ix/cord-v2")`) |
| **Splits provided** | `train` (800), `validation` (100), `test` (100) |
| **Download script** | `scripts/download_datasets.py --cord` |
| **Data directory** | `data/cord/{train,validation,test}/` (git-ignored) |
| **License** | CC BY 4.0 |
| **Citation** | Park, S., et al. (2019). CORD: A Consolidated Receipt Dataset for Post-OCR Parsing. NeurIPS 2019 Workshop. |

### 5.2 SROIE

| Field | Value |
|---|---|
| **Origin** | ICDAR 2019 Robust Reading Challenge on Scanned Receipts OCR and IE |
| **HF mirror** | `jinhybr/OCR-SROIE-2019` or Kaggle `urbikn/sroie-datasetv2` |
| **Download method** | Manual — see `python scripts/download_datasets.py --sroie` for instructions |
| **Splits provided** | `train` (~626 receipts), `test` (~347 receipts) |
| **Data directory** | `data/sroie/{train,test}/` (git-ignored) |
| **License** | ICDAR 2019 competition terms — research/academic use |
| **Citation** | Huang, Z., et al. (2019). ICDAR 2019 Competition on Scanned Receipt OCR and Information Extraction. ICDAR 2019. |
| **Note on label noise** | ~3–5% of labels have minor transcription errors. Flagged records are excluded from the dev and test manifests if found. |

### 5.3 Synthetic Invoices

| Field | Value |
|---|---|
| **Generator** | `scripts/generate_invoices.py` |
| **Ground truth source** | Directly from `Faker` data models — 100% exact |
| **Number of templates** | 4 (classic_table, modern_minimal, two_column, thermal_compact) |
| **Currencies** | USD, EUR, GBP, PKR, AED |
| **Total generated** | 500 (200 dev, 400 test) — runs locally with no internet |
| **Hard cases** | ~30% include: multi-line items, page overflow, European numbers, previous balance lines |

### 5.4 Currency Inference Note

For CORD and SROIE, the document currency is **inferred** from dataset provenance, not extracted from labels:

- **CORD** → `IDR` (Indonesian Rupiah) — all receipts are from Indonesia
- **SROIE** → `MYR` (Malaysian Ringgit) — all receipts are from Malaysia

Currency is only scored against ground truth for **synthetic invoices**, where it is truly labeled.
