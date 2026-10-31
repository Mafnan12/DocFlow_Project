# Datasets and Ground Truth Documentation

DocFlow evaluates performance across public receipt datasets and synthetic invoice generators with exact ground truth.

## 1. Public Datasets

### CORD v2 (Consolidated Receipt Dataset for Post-OCR Parsing)
- **Source:** Hugging Face (`naver-clova-ix/cord-v2`)
- **Origin:** Naver Clova / Indonesian receipts
- **Content:** Camera photos of receipts, containing line items (name, count, unit price, total price), subtotal, tax, service charges, discounts, and total.
- **Currency:** Indonesian Rupiah (IDR).
- **Format Notes:** Thousands separators often use dots (e.g., `60.000`).
- **License:** Creative Commons Attribution 4.0 International (CC-BY 4.0).
- **Mask:** Line items, subtotal, tax, service charge, discount, total. (Vendor name/date are unmasked where present or masked if unannotated).

### SROIE (ICDAR 2019 Scanned Receipts OCR and Information Extraction)
- **Source:** ICDAR 2019 Robust Reading Competition
- **Origin:** Malaysian scanned receipts
- **Content:** Scanned receipts with labels for `company`, `date`, `address`, and `total`.
- **Currency:** Malaysian Ringgit (MYR).
- **Format Notes:** Multiple date notations (e.g., DD/MM/YYYY, DD-MMM-YY). Known minor label noise in totals.
- **License:** Research use per ICDAR 2019 competition terms.
- **Mask:** `vendor_name`, `date`, `total`. Line items are not annotated and thus masked during scoring.

## 2. Synthetic Invoices
- **Generator:** Jinja2 HTML templates rendered to PDF via WeasyPrint / ReportLab, with data generated via `Faker`.
- **Content:** Full ground-truth coverage across all schema fields: vendor details, customer details, invoice numbers, dates, line items, taxes, discounts, and totals across diverse currencies (USD, EUR, GBP, PKR, AED).
- **Degradation Suite:** Simulated real-world camera flaws via OpenCV (Gaussian blur, salt-and-pepper noise, skew, rotation, contrast variations).

## 3. Dataset Splits & Discipline
- **Dev Split:** Used exclusively for prompt engineering, confidence weight calibration, and threshold sweeps.
- **Test Split:** Held out completely until final benchmark reporting. Never tuned on test data.
