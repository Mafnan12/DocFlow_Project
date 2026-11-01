"""Convert dataset-specific labels to the unified DocFlow ground-truth format.

Usage:
    python scripts/convert_ground_truth.py --cord
    python scripts/convert_ground_truth.py --sroie
    python scripts/convert_ground_truth.py --all

Unified GT format (per docs/DATA.md and spec Section 9.2):

{
  "doc_id": "cord_test_0042",
  "source": "cord",          # "cord" | "sroie" | "synthetic"
  "file": "data/cord/test/0042.png",
  "doc_type": "receipt",
  "labeled_fields": [...],   # evaluation mask — only these fields are scored
  "ground_truth": {
    "vendor_name": null | str,
    "vendor_address": null | str,
    "invoice_number": null | str,
    "date": null | str,      # "YYYY-MM-DD" if parseable, else as printed
    "currency": "IDR",
    "line_items": [...],
    "subtotal": null | str,  # canonical: digits + "." separator, no symbols
    "tax": null | str,
    "service_charge": null | str,
    "discount": null | str,
    "rounding": null | str,
    "total": null | str
  }
}

Amounts are stored as canonical strings: digits with "." as the only
decimal separator, no thousands separators, no currency symbols.
The same normalization functions used in the pipeline are used here.

IMPORTANT: this script reads data/ which is git-ignored.
Run download_datasets.py first.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
GT_DIR = DATA_DIR / "ground_truth"

# ---------------------------------------------------------------------------
# Canonical amount normalization
# ---------------------------------------------------------------------------

_IDR_THOUSANDS_RE = re.compile(r"^(\d{1,3})(\.\d{3})+$")
_EUROPEAN_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)$")


def to_canonical_amount(raw: str | None) -> str | None:
    """Convert a printed amount string to canonical form.

    Canonical form: digits + "." as decimal separator, no thousands separators,
    no currency symbols or whitespace. E.g. "60.000" (IDR) → "60000",
    "1.234,56" (European) → "1234.56", "RM 12.50" → "12.50".

    Returns None if raw is None or empty.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None

    # Strip common currency symbols and codes
    s = re.sub(r"(?i)(rm|idr|usd|eur|gbp|myr|\$|€|£|¥|₹)\s*", "", s).strip()
    if not s:
        return None

    # European format: 1.234,56  →  1234.56
    if _EUROPEAN_RE.match(s):
        s = s.replace(".", "").replace(",", ".")
        return s

    # IDR thousands: 60.000 → 60000  (only if no decimal comma follows)
    if _IDR_THOUSANDS_RE.match(s):
        s = s.replace(".", "")
        return s

    # Western format: remove commas used as thousands separators
    # e.g. "1,234.56" → "1234.56"
    if re.match(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$", s):
        s = s.replace(",", "")
        return s

    # Plain number (possibly with decimal dot already)
    if re.match(r"^-?\d+(\.\d+)?$", s):
        return s

    # Fallback: strip any remaining non-numeric chars except dot and minus
    cleaned = re.sub(r"[^\d.\-]", "", s)
    return cleaned if cleaned else None


def parse_date_to_iso(raw: str | None) -> str | None:
    """Best-effort parse of printed dates to ISO YYYY-MM-DD.

    Returns the raw string unchanged if it cannot be parsed confidently.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None

    # Already ISO
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # DD/MM/YYYY or DD-MM-YYYY (common in SROIE / Malaysia)
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    # MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        mo, d, y = m.group(1), m.group(2), m.group(3)
        # Heuristic: if month > 12, must be day-first
        if int(mo) > 12:
            return f"{y}-{d.zfill(2)}-{mo.zfill(2)}"
        return f"{y}-{mo.zfill(2)}-{d.zfill(2)}"

    # "25 Jan 2020" etc.
    month_abbr = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    m = re.match(r"^(\d{1,2})\s+([a-zA-Z]+)\s+(\d{4})$", s)
    if m:
        d, mon, y = m.group(1), m.group(2).lower()[:3], m.group(3)
        if mon in month_abbr:
            return f"{y}-{month_abbr[mon]}-{d.zfill(2)}"

    # Return as-is (scorer will mark as unparsed)
    return s


# ---------------------------------------------------------------------------
# CORD v2 converter
# ---------------------------------------------------------------------------

# CORD labeled fields per spec Section 9.2
CORD_LABELED_FIELDS = [
    "line_items",
    "subtotal",
    "tax",
    "service_charge",
    "discount",
    "total",
]


def _cord_parse_menu(menu_items: list[dict]) -> list[dict]:
    """Extract line items from CORD's 'menu' key."""
    items: list[dict] = []
    for m in menu_items:
        items.append(
            {
                "description": m.get("nm", ""),
                "quantity": to_canonical_amount(str(m["cnt"])) if m.get("cnt") else None,
                "unit_price": to_canonical_amount(m.get("price")),
                "total": to_canonical_amount(m.get("unitprice")),
            }
        )
    return items


def _cord_sum_field(sub_data: dict, key: str) -> str | None:
    """Sum repeated subfields in CORD (e.g. multiple tax entries)."""
    vals = sub_data.get(key)
    if vals is None:
        return None
    if isinstance(vals, list):
        total = 0.0
        for v in vals:
            canon = to_canonical_amount(str(v) if not isinstance(v, str) else v)
            if canon:
                try:
                    total += float(canon)
                except ValueError:
                    pass
        # Format without trailing .0 when integer
        if total == int(total):
            return str(int(total))
        return f"{total:.2f}"
    canon = to_canonical_amount(str(vals) if not isinstance(vals, str) else vals)
    return canon


def convert_cord_example(idx: int, split: str, raw_gt: dict) -> dict[str, Any]:
    """Convert one CORD example to the unified GT format."""
    gt_data = raw_gt.get("gt_parse", raw_gt)

    sub_total_data: dict = {}
    if "sub_total" in gt_data:
        sub_total_data = gt_data["sub_total"]
        if isinstance(sub_total_data, list):
            # Merge list of sub_total dicts
            merged: dict = {}
            for item in sub_total_data:
                merged.update(item)
            sub_total_data = merged

    menu_items = gt_data.get("menu", [])
    if not isinstance(menu_items, list):
        menu_items = []

    line_items = _cord_parse_menu(menu_items)

    # CORD total lives in gt_parse.total_price.total_price (confusingly named)
    total_price_data: dict = gt_data.get("total_price", {})
    if isinstance(total_price_data, list):
        tp_merged: dict = {}
        for item in total_price_data:
            tp_merged.update(item)
        total_price_data = tp_merged

    total_raw = total_price_data.get("total_price") or sub_total_data.get("total_price")
    subtotal_raw = sub_total_data.get("subtotal_price")
    tax_raw = _cord_sum_field(sub_total_data, "tax_price")
    service_raw = _cord_sum_field(sub_total_data, "service_price")
    discount_raw = _cord_sum_field(sub_total_data, "discount_price")

    return {
        "doc_id": f"cord_{split}_{idx:04d}",
        "source": "cord",
        "file": f"data/cord/{split}/{idx:04d}.png",
        "doc_type": "receipt",
        "labeled_fields": CORD_LABELED_FIELDS,
        "ground_truth": {
            "vendor_name": None,  # CORD does not label vendor name
            "vendor_address": None,
            "invoice_number": None,
            "date": None,
            "currency": "IDR",  # CORD is Indonesian receipts — inferred
            "line_items": line_items,
            "subtotal": to_canonical_amount(subtotal_raw),
            "tax": tax_raw,
            "service_charge": service_raw,
            "discount": discount_raw,
            "rounding": None,
            "total": to_canonical_amount(total_raw),
        },
    }


def convert_cord(splits: list[str] | None = None) -> None:
    """Convert CORD splits to unified GT JSONL files."""
    if splits is None:
        splits = ["train", "validation", "test"]

    GT_DIR.mkdir(parents=True, exist_ok=True)

    for split in splits:
        split_dir = DATA_DIR / "cord" / split
        if not split_dir.exists():
            log.warning(
                "CORD %s split not found at %s — skipping. Run download_datasets.py first.",
                split,
                split_dir,
            )
            continue

        image_paths = sorted(split_dir.glob("*.png"))
        if not image_paths:
            log.warning("No images found in %s — skipping.", split_dir)
            continue

        out_path = GT_DIR / f"cord_{split}.jsonl"
        count = 0
        with out_path.open("w", encoding="utf-8") as f:
            for img_path in image_paths:
                idx = int(img_path.stem)
                gt_json_path = split_dir / f"{img_path.stem}.json"
                raw_gt: dict = {}
                if gt_json_path.exists():
                    raw_gt = json.loads(gt_json_path.read_text(encoding="utf-8"))

                record = convert_cord_example(idx, split, raw_gt)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

        log.info("CORD %s: wrote %d records to %s", split, count, out_path)


# ---------------------------------------------------------------------------
# SROIE converter
# ---------------------------------------------------------------------------

# SROIE labeled fields per spec Section 9.1
SROIE_LABELED_FIELDS = ["vendor_name", "date", "total"]

# SROIE also has "address" but it's noisy; scored separately in the eval mask


def _read_sroie_entities(entities_path: Path) -> dict[str, str]:
    """Parse a SROIE entities file (key:value lines)."""
    entities: dict[str, str] = {}
    for line in entities_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if ":" in line:
            key, _, value = line.partition(":")
            entities[key.strip().lower()] = value.strip()
    return entities


def convert_sroie_example(idx: int, split: str, img_path: Path, entities: dict) -> dict[str, Any]:
    """Convert one SROIE example to the unified GT format."""
    raw_date = entities.get("date")
    raw_total = entities.get("total")
    vendor_name = entities.get("company")
    address = entities.get("address")

    # Build a portable relative file path regardless of whether img_path is
    # absolute or already relative to the repo root.
    if img_path.is_absolute():
        try:
            rel = img_path.relative_to(REPO_ROOT)
        except ValueError:
            rel = img_path  # fallback: keep as-is
        file_str = str(rel).replace("\\", "/")
    else:
        file_str = str(img_path).replace("\\", "/")

    return {
        "doc_id": f"sroie_{split}_{idx:04d}",
        "source": "sroie",
        "file": file_str,
        "doc_type": "receipt",
        "labeled_fields": SROIE_LABELED_FIELDS,
        "ground_truth": {
            "vendor_name": vendor_name,
            "vendor_address": address,
            "invoice_number": None,
            "date": parse_date_to_iso(raw_date),
            "currency": "MYR",  # SROIE is Malaysian receipts — inferred
            "line_items": [],  # SROIE does not label line items
            "subtotal": None,
            "tax": None,
            "service_charge": None,
            "discount": None,
            "rounding": None,
            "total": to_canonical_amount(raw_total),
        },
    }


def convert_sroie(splits: list[str] | None = None) -> None:
    """Convert SROIE splits to unified GT JSONL files."""
    if splits is None:
        splits = ["train", "test"]

    GT_DIR.mkdir(parents=True, exist_ok=True)

    for split in splits:
        split_dir = DATA_DIR / "sroie" / split
        entities_dir = split_dir / "entities"

        if not split_dir.exists():
            log.warning(
                "SROIE %s split not found at %s — skipping. "
                "Run: python scripts/download_datasets.py --sroie (for instructions).",
                split,
                split_dir,
            )
            continue

        if not entities_dir.exists():
            log.warning(
                "SROIE entities dir not found at %s. "
                "Expected structure: data/sroie/%s/entities/<id>.txt",
                entities_dir,
                split,
            )
            continue

        image_paths = sorted(split_dir.glob("*.jpg")) + sorted(split_dir.glob("*.png"))
        if not image_paths:
            log.warning("No images found in %s — skipping.", split_dir)
            continue

        out_path = GT_DIR / f"sroie_{split}.jsonl"
        count = 0
        with out_path.open("w", encoding="utf-8") as f:
            for idx, img_path in enumerate(image_paths):
                entity_path = entities_dir / (img_path.stem + ".txt")
                entities: dict[str, str] = {}
                if entity_path.exists():
                    entities = _read_sroie_entities(entity_path)
                else:
                    log.debug("No entity file for %s", img_path.name)

                record = convert_sroie_example(idx, split, img_path, entities)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

        log.info("SROIE %s: wrote %d records to %s", split, count, out_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert dataset labels to the unified DocFlow ground-truth format."
    )
    parser.add_argument("--cord", action="store_true", help="Convert CORD v2")
    parser.add_argument("--sroie", action="store_true", help="Convert SROIE")
    parser.add_argument("--all", dest="all_", action="store_true", help="Convert both")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not (args.cord or args.sroie or args.all_):
        print("No action specified. Use --cord, --sroie, or --all.")
        print("Run with --help for usage.")
        return

    if args.cord or args.all_:
        convert_cord()

    if args.sroie or args.all_:
        convert_sroie()


if __name__ == "__main__":
    main()
