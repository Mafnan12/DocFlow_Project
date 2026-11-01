"""Tests for T05 synthetic invoice generation."""

from __future__ import annotations

import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from faker import Faker
from generate_invoices import build_invoice, generate_invoices


def _test_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "data" / "_t05_test_artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_build_invoice_has_exact_decimal_arithmetic() -> None:
    record = build_invoice(0, random.Random(42), Faker(), hard_case_rate=1.0)
    ground_truth = record["ground_truth"]

    item_sum = sum((Decimal(item["total"]) for item in ground_truth["line_items"]), Decimal("0"))
    subtotal = Decimal(ground_truth["subtotal"])
    discount = Decimal(ground_truth["discount"] or "0")
    tax = Decimal(ground_truth["tax"] or "0")
    service_charge = Decimal(ground_truth["service_charge"] or "0")

    assert item_sum == subtotal
    assert Decimal(ground_truth["total"]) == subtotal - discount + tax + service_charge
    assert ground_truth["currency"] in {"USD", "EUR", "GBP", "PKR", "AED"}
    assert record["render_metadata"]["hard_case"] is True


def test_generate_invoices_writes_all_artifacts_and_four_layouts() -> None:
    test_root = _test_root() / "four-layouts"
    output_dir = test_root / "synthetic"
    ground_truth_path = test_root / "ground_truth.jsonl"
    manifest_path = output_dir / "manifest.jsonl"

    records = generate_invoices(
        count=4,
        output_dir=output_dir,
        ground_truth_path=ground_truth_path,
        manifest_path=manifest_path,
        seed=42,
    )

    assert len(records) == 4
    assert {record["render_metadata"]["template"] for record in records} == {
        "classic_table.html",
        "modern_minimal.html",
        "two_column.html",
        "thermal_compact.html",
    }
    assert any(record["render_metadata"]["page_count"] > 1 for record in records)
    assert ground_truth_path.exists()
    assert manifest_path.exists()

    serialized_records = [
        json.loads(line) for line in ground_truth_path.read_text(encoding="utf-8").splitlines()
    ]
    assert [record["doc_id"] for record in serialized_records] == [
        "synthetic_0000",
        "synthetic_0001",
        "synthetic_0002",
        "synthetic_0003",
    ]
    for record in records:
        assert Path(record["file"]).exists()
        assert Path(record["pdf_file"]).exists()
        assert Path(record["html_file"]).exists()
        assert record["ground_truth"]["total"] is not None


def test_generation_is_reproducible_for_source_data() -> None:
    test_root = _test_root() / "reproducibility"
    first = generate_invoices(
        count=3,
        output_dir=test_root / "first",
        ground_truth_path=test_root / "first.jsonl",
        manifest_path=test_root / "first-manifest.jsonl",
        seed=123,
    )
    second = generate_invoices(
        count=3,
        output_dir=test_root / "second",
        ground_truth_path=test_root / "second.jsonl",
        manifest_path=test_root / "second-manifest.jsonl",
        seed=123,
    )

    assert [record["ground_truth"] for record in first] == [
        record["ground_truth"] for record in second
    ]
    assert [record["render_metadata"] for record in first] == [
        record["render_metadata"] for record in second
    ]
