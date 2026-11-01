"""Download datasets for DocFlow evaluation.

Usage:
    python scripts/download_datasets.py [--cord] [--sroie] [--all]

Downloads:
  CORD v2  — via Hugging Face `datasets` library (no auth required)
  SROIE    — prints instructions (manual download required)

All data is saved to data/ which is git-ignored.
Licenses and sources are recorded in docs/DATA.md.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
CORD_DIR = DATA_DIR / "cord"
SROIE_DIR = DATA_DIR / "sroie"

CORD_HF_NAME = "naver-clova-ix/cord-v2"

# ---------------------------------------------------------------------------
# CORD v2
# ---------------------------------------------------------------------------


def download_cord() -> None:
    """Download CORD v2 from Hugging Face and save images to data/cord/."""
    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SystemExit(
            "The `datasets` package is not installed. Run:\n"
            "  python -m uv pip install datasets\n"
            "or add it to pyproject.toml and re-sync."
        ) from exc

    log.info("Downloading CORD v2 from Hugging Face (%s) …", CORD_HF_NAME)
    dataset = load_dataset(CORD_HF_NAME)

    split_map = {
        "train": dataset["train"],
        "validation": dataset["validation"],
        "test": dataset["test"],
    }

    total = 0
    for split_name, split_data in split_map.items():
        split_dir = CORD_DIR / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        log.info("  Saving %d images to %s …", len(split_data), split_dir)

        for idx, example in enumerate(split_data):
            img_path = split_dir / f"{idx:04d}.png"
            if not img_path.exists():
                example["image"].save(img_path)

            gt_path = split_dir / f"{idx:04d}.json"
            if not gt_path.exists():
                # Preserve the raw CORD annotation verbatim
                raw_gt: dict = {}
                if "ground_truth" in example:
                    gt_val = example["ground_truth"]
                    if isinstance(gt_val, str):
                        raw_gt = json.loads(gt_val)
                    elif isinstance(gt_val, dict):
                        raw_gt = gt_val
                gt_path.write_text(
                    json.dumps(raw_gt, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            total += 1

        log.info("  Done: %d examples in '%s' split.", len(split_data), split_name)

    log.info("CORD v2 download complete — %d total images.", total)
    _write_manifest(CORD_DIR, "cord")


def _write_manifest(root: Path, source: str) -> None:
    """Write a simple file-count manifest to root/manifest.json."""
    counts = {
        split: len(list((root / split).glob("*.png")))
        for split in ("train", "validation", "test")
        if (root / split).exists()
    }
    manifest = {"source": source, "splits": counts}
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("Wrote manifest: %s", manifest_path)


# ---------------------------------------------------------------------------
# SROIE
# ---------------------------------------------------------------------------

SROIE_INSTRUCTIONS = """
================================================================================
SROIE DOWNLOAD INSTRUCTIONS
================================================================================
SROIE (ICDAR 2019 Robust Reading Challenge on Scanned Receipts OCR and
Information Extraction) is NOT available for automatic download because the
original competition site requires registration and the Kaggle mirrors require
a Kaggle account.

Steps to download manually:

Option A — Hugging Face mirror (no Kaggle account needed):
  1. Go to: https://huggingface.co/datasets/jinhybr/OCR-SROIE-2019
  2. Click "Files and versions" → download the zip archives.
  3. Extract to: {sroie_dir}/

Option B — Kaggle:
  1. Install the Kaggle CLI: pip install kaggle
  2. Set up your API key: https://www.kaggle.com/docs/api
  3. Run:
       kaggle datasets download -d urbikn/sroie-datasetv2 -p {sroie_dir} --unzip

Expected structure after extraction:
  data/sroie/train/
    <id>.jpg
    <id>.txt       (OCR bounding boxes)
  data/sroie/train/entities/
    <id>.txt       (key-value pairs: company, date, address, total)
  data/sroie/test/
    <same structure>

License:
  SROIE is an ICDAR competition dataset. Usage is for research purposes.
  Cite: ICDAR 2019 Robust Reading Challenge on SROIE.
================================================================================
"""


def show_sroie_instructions() -> None:
    print(SROIE_INSTRUCTIONS.format(sroie_dir=SROIE_DIR))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download datasets for DocFlow evaluation.")
    parser.add_argument("--cord", action="store_true", help="Download CORD v2")
    parser.add_argument("--sroie", action="store_true", help="Print SROIE instructions")
    parser.add_argument("--all", dest="all_", action="store_true", help="Do both")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not (args.cord or args.sroie or args.all_):
        print("No action specified. Use --cord, --sroie, or --all.")
        print("Run with --help for usage.")
        return

    if args.cord or args.all_:
        download_cord()

    if args.sroie or args.all_:
        show_sroie_instructions()


if __name__ == "__main__":
    main()
