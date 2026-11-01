"""Tests for T05 deterministic image degradations and manifests."""

from __future__ import annotations

import json
import random
from pathlib import Path

import cv2
import numpy as np

from scripts.degrade_images import degrade_image, degrade_manifest


def test_degrade_image_is_reproducible() -> None:
    image = np.full((80, 120, 3), 220, dtype=np.uint8)
    image[20:60, 30:90] = 30

    first_image, first_specs = degrade_image(
        image, random.Random(99), operations=["rotation", "noise"]
    )
    second_image, second_specs = degrade_image(
        image, random.Random(99), operations=["rotation", "noise"]
    )

    assert first_specs == second_specs
    assert np.array_equal(first_image, second_image)
    assert not np.array_equal(first_image, image)


def test_degrade_manifest_records_parameters_and_paths() -> None:
    test_root = Path(__file__).resolve().parents[2] / "data" / "_t05_test_artifacts" / "degradation"
    test_root.mkdir(parents=True, exist_ok=True)
    image_path = test_root / "invoice.png"
    image = np.full((100, 160, 3), 255, dtype=np.uint8)
    cv2.putText(image, "INVOICE", (20, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    assert cv2.imwrite(str(image_path), image)

    input_manifest = test_root / "manifest.jsonl"
    input_manifest.write_text(
        json.dumps(
            {
                "doc_id": "synthetic_0000",
                "source": "synthetic",
                "file": str(image_path),
                "image_file": str(image_path),
                "ground_truth": {"total": "10.00"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = test_root / "degraded"
    output_manifest = test_root / "degraded_manifest.jsonl"

    records = degrade_manifest(
        input_dir=test_root,
        input_manifest=input_manifest,
        output_dir=output_dir,
        output_manifest=output_manifest,
        fraction=1.0,
        seed=42,
        min_operations=2,
        max_operations=2,
    )

    assert len(records) == 1
    record = records[0]
    assert record["degraded"] is True
    assert len(record["degradations"]) == 2
    assert record["degradation_types"] == [item["type"] for item in record["degradations"]]
    assert Path(record["file"]).exists()
    assert output_manifest.exists()
    assert cv2.imread(record["file"]).shape == image.shape
