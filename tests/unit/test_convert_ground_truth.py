"""Unit tests for T04: dataset download helpers and GT conversion.

Tests exercise:
- to_canonical_amount: IDR thousands, European format, Western commas, plain
- parse_date_to_iso: DD/MM/YYYY, ISO passthrough, named month
- convert_cord_example: full CORD GT → unified format
- convert_sroie_example: SROIE entities → unified format

These run without any data on disk (all inputs are in-memory).
"""

from __future__ import annotations

import json

# We import the converter module directly from scripts/
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from convert_ground_truth import (
    CORD_LABELED_FIELDS,
    SROIE_LABELED_FIELDS,
    convert_cord_example,
    convert_sroie_example,
    parse_date_to_iso,
    to_canonical_amount,
)

# ---------------------------------------------------------------------------
# to_canonical_amount
# ---------------------------------------------------------------------------


class TestToCanonicalAmount:
    def test_none_returns_none(self) -> None:
        assert to_canonical_amount(None) is None

    def test_empty_returns_none(self) -> None:
        assert to_canonical_amount("") is None
        assert to_canonical_amount("   ") is None

    def test_idr_thousands_60000(self) -> None:
        """Indonesian '60.000' (sixty thousand) → '60000'."""
        assert to_canonical_amount("60.000") == "60000"

    def test_idr_thousands_1200000(self) -> None:
        assert to_canonical_amount("1.200.000") == "1200000"

    def test_european_format(self) -> None:
        """European '1.234,56' → '1234.56'."""
        assert to_canonical_amount("1.234,56") == "1234.56"

    def test_western_commas(self) -> None:
        """Western '1,234.56' → '1234.56'."""
        assert to_canonical_amount("1,234.56") == "1234.56"

    def test_plain_decimal(self) -> None:
        assert to_canonical_amount("12.50") == "12.50"

    def test_plain_integer(self) -> None:
        assert to_canonical_amount("55000") == "55000"

    def test_strips_rm_prefix(self) -> None:
        assert to_canonical_amount("RM 12.50") == "12.50"

    def test_strips_idr_prefix(self) -> None:
        assert to_canonical_amount("IDR 60.000") == "60000"

    def test_negative_amount(self) -> None:
        assert to_canonical_amount("-0.02") == "-0.02"

    def test_zero(self) -> None:
        assert to_canonical_amount("0") == "0"

    def test_simple_with_cents(self) -> None:
        assert to_canonical_amount("25000") == "25000"


# ---------------------------------------------------------------------------
# parse_date_to_iso
# ---------------------------------------------------------------------------


class TestParseDateToIso:
    def test_iso_passthrough(self) -> None:
        assert parse_date_to_iso("2023-07-15") == "2023-07-15"

    def test_dd_mm_yyyy_slash(self) -> None:
        assert parse_date_to_iso("25/07/2023") == "2023-07-25"

    def test_dd_mm_yyyy_hyphen(self) -> None:
        assert parse_date_to_iso("25-07-2023") == "2023-07-25"

    def test_named_month(self) -> None:
        assert parse_date_to_iso("25 Jan 2020") == "2020-01-25"

    def test_named_month_case_insensitive(self) -> None:
        assert parse_date_to_iso("3 DEC 2021") == "2021-12-03"

    def test_unknown_format_passthrough(self) -> None:
        """Unrecognised format is returned as-is."""
        raw = "July 25th, 2023"
        assert parse_date_to_iso(raw) == raw

    def test_none_returns_none(self) -> None:
        assert parse_date_to_iso(None) is None

    def test_empty_returns_none(self) -> None:
        assert parse_date_to_iso("") is None


# ---------------------------------------------------------------------------
# convert_cord_example
# ---------------------------------------------------------------------------


CORD_RAW_GT = {
    "gt_parse": {
        "menu": [
            {"nm": "ICED AMERICANO", "cnt": "2", "unitprice": "50000"},
        ],
        "sub_total": {
            "subtotal_price": "50000",
            "tax_price": "5000",
        },
        "total_price": {
            "total_price": "55000",
        },
    }
}


class TestConvertCordExample:
    def test_doc_id_format(self) -> None:
        rec = convert_cord_example(42, "test", CORD_RAW_GT)
        assert rec["doc_id"] == "cord_test_0042"

    def test_source_and_doc_type(self) -> None:
        rec = convert_cord_example(0, "train", CORD_RAW_GT)
        assert rec["source"] == "cord"
        assert rec["doc_type"] == "receipt"

    def test_currency_inferred_idr(self) -> None:
        rec = convert_cord_example(0, "test", CORD_RAW_GT)
        assert rec["ground_truth"]["currency"] == "IDR"

    def test_labeled_fields(self) -> None:
        rec = convert_cord_example(0, "test", CORD_RAW_GT)
        assert rec["labeled_fields"] == CORD_LABELED_FIELDS

    def test_total_parsed(self) -> None:
        rec = convert_cord_example(42, "test", CORD_RAW_GT)
        assert rec["ground_truth"]["total"] == "55000"

    def test_subtotal_parsed(self) -> None:
        rec = convert_cord_example(42, "test", CORD_RAW_GT)
        assert rec["ground_truth"]["subtotal"] == "50000"

    def test_tax_parsed(self) -> None:
        rec = convert_cord_example(42, "test", CORD_RAW_GT)
        assert rec["ground_truth"]["tax"] == "5000"

    def test_line_items(self) -> None:
        rec = convert_cord_example(42, "test", CORD_RAW_GT)
        items = rec["ground_truth"]["line_items"]
        assert len(items) == 1
        assert items[0]["description"] == "ICED AMERICANO"
        assert items[0]["total"] == "50000"

    def test_empty_gt(self) -> None:
        """Empty ground truth should not raise."""
        rec = convert_cord_example(0, "test", {})
        assert rec["ground_truth"]["total"] is None
        assert rec["ground_truth"]["line_items"] == []

    def test_file_path_format(self) -> None:
        rec = convert_cord_example(7, "validation", CORD_RAW_GT)
        assert rec["file"] == "data/cord/validation/0007.png"


# ---------------------------------------------------------------------------
# convert_sroie_example
# ---------------------------------------------------------------------------


class TestConvertSroieExample:
    def _make_entities(self) -> dict[str, str]:
        return {
            "company": "AEON CO. (M) BHD.",
            "date": "25/07/2019",
            "address": "LOT 1.16, LEVEL 1, AEON",
            "total": "RM 55.80",
        }

    def test_doc_id_format(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(3, "train", Path("data/sroie/train/0003.jpg"), entities)
        assert rec["doc_id"] == "sroie_train_0003"

    def test_source_and_doc_type(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["source"] == "sroie"
        assert rec["doc_type"] == "receipt"

    def test_currency_inferred_myr(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["ground_truth"]["currency"] == "MYR"

    def test_labeled_fields(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["labeled_fields"] == SROIE_LABELED_FIELDS

    def test_date_iso_converted(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["ground_truth"]["date"] == "2019-07-25"

    def test_total_strips_rm(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["ground_truth"]["total"] == "55.80"

    def test_vendor_name(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["ground_truth"]["vendor_name"] == "AEON CO. (M) BHD."

    def test_empty_entities(self) -> None:
        """Missing entities should not raise."""
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), {})
        assert rec["ground_truth"]["vendor_name"] is None
        assert rec["ground_truth"]["total"] is None

    def test_line_items_empty(self) -> None:
        """SROIE does not label line items."""
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        assert rec["ground_truth"]["line_items"] == []

    def test_gt_is_json_serializable(self) -> None:
        entities = self._make_entities()
        rec = convert_sroie_example(0, "test", Path("data/sroie/test/0000.jpg"), entities)
        # Must not raise
        _ = json.dumps(rec)
