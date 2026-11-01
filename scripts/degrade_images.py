"""Apply deterministic camera and scan degradations to invoice images.

Each selected image receives one to three independent degradations. The output
manifest records both the operation names and their sampled parameters so
evaluation and error analysis can group failures by degradation type.

Usage:
    python scripts/degrade_images.py --fraction 0.5
    python scripts/degrade_images.py --fraction 1 --seed 42
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_DIR = REPO_ROOT / "data" / "synthetic" / "images"
DEFAULT_INPUT_MANIFEST = REPO_ROOT / "data" / "synthetic" / "manifest.jsonl"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "synthetic" / "degraded"
DEFAULT_OUTPUT_MANIFEST = REPO_ROOT / "data" / "synthetic" / "degraded_manifest.jsonl"

DEGRADATION_TYPES = (
    "rotation",
    "perspective",
    "gaussian_blur",
    "motion_blur",
    "jpeg_compression",
    "noise",
    "low_contrast",
    "shadow",
)

log = logging.getLogger(__name__)


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def _resolve_source_path(value: str, input_dir: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    repo_candidate = REPO_ROOT / candidate
    return repo_candidate if repo_candidate.exists() else input_dir / candidate.name


def choose_degradations(
    rng: random.Random,
    min_operations: int = 1,
    max_operations: int = 3,
) -> list[str]:
    """Choose unique operation names using a caller-provided deterministic RNG."""

    if min_operations < 1 or max_operations < min_operations:
        raise ValueError("operation bounds must satisfy 1 <= min_operations <= max_operations")
    max_operations = min(max_operations, len(DEGRADATION_TYPES))
    count = rng.randint(min_operations, max_operations)
    return rng.sample(list(DEGRADATION_TYPES), count)


def _rotate(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, matrix, (width, height), borderValue=(255, 255, 255))


def _perspective(image: np.ndarray, amount: float) -> np.ndarray:
    height, width = image.shape[:2]
    shift_x = width * amount
    shift_y = height * amount
    source = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    target = np.float32(
        [
            [shift_x, shift_y],
            [width - 1 - shift_x, 0],
            [width - 1, height - 1 - shift_y],
            [0, height - 1],
        ]
    )
    matrix = cv2.getPerspectiveTransform(source, target)
    return cv2.warpPerspective(image, matrix, (width, height), borderValue=(255, 255, 255))


def _motion_blur(image: np.ndarray, kernel_size: int, horizontal: bool) -> np.ndarray:
    kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)
    if horizontal:
        kernel[kernel_size // 2, :] = 1 / kernel_size
    else:
        kernel[:, kernel_size // 2] = 1 / kernel_size
    return cv2.filter2D(image, -1, kernel)


def _add_shadow(image: np.ndarray, strength: float, start: float) -> np.ndarray:
    height, width = image.shape[:2]
    gradient = np.ones((height, width), dtype=np.float32)
    start_row = int(height * start)
    shadow_height = max(1, height - start_row)
    gradient[start_row:, :] = np.linspace(1.0 - strength, 1.0, shadow_height)[:, None]
    result = image.astype(np.float32) * gradient[:, :, None]
    return np.clip(result, 0, 255).astype(np.uint8)


def _apply_operation(
    image: np.ndarray,
    operation: str,
    rng: random.Random,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply one named operation and return the sampled parameters."""

    if operation == "rotation":
        angle = round(rng.uniform(-5.0, 5.0), 2)
        return _rotate(image, angle), {"type": operation, "angle_degrees": angle}
    if operation == "perspective":
        amount = round(rng.uniform(0.03, 0.10), 3)
        return _perspective(image, amount), {"type": operation, "corner_shift_fraction": amount}
    if operation == "gaussian_blur":
        kernel_size = rng.choice((3, 5, 7))
        return cv2.GaussianBlur(image, (kernel_size, kernel_size), 0), {
            "type": operation,
            "kernel_size": kernel_size,
        }
    if operation == "motion_blur":
        kernel_size = rng.choice((3, 5, 7))
        horizontal = rng.choice((True, False))
        return _motion_blur(image, kernel_size, horizontal), {
            "type": operation,
            "kernel_size": kernel_size,
            "direction": "horizontal" if horizontal else "vertical",
        }
    if operation == "jpeg_compression":
        quality = rng.randint(30, 70)
        success, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not success:
            raise RuntimeError("OpenCV could not encode the image as JPEG")
        decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if decoded is None:
            raise RuntimeError("OpenCV could not decode the compressed JPEG")
        return decoded, {"type": operation, "quality": quality}
    if operation == "noise":
        sigma = round(rng.uniform(5.0, 18.0), 2)
        noise_seed = rng.randint(0, 2**32 - 1)
        noise_rng = np.random.default_rng(noise_seed)
        noise = noise_rng.normal(0, sigma, image.shape)
        noisy = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        return noisy, {"type": operation, "sigma": sigma, "seed": noise_seed}
    if operation == "low_contrast":
        alpha = round(rng.uniform(0.45, 0.75), 3)
        beta = rng.randint(20, 80)
        return cv2.convertScaleAbs(image, alpha=alpha, beta=beta), {
            "type": operation,
            "alpha": alpha,
            "beta": beta,
        }
    if operation == "shadow":
        strength = round(rng.uniform(0.25, 0.55), 3)
        start = round(rng.uniform(0.15, 0.65), 3)
        return _add_shadow(image, strength, start), {
            "type": operation,
            "strength": strength,
            "start_fraction": start,
        }
    raise ValueError(f"Unknown degradation operation: {operation}")


def degrade_image(
    image: np.ndarray,
    rng: random.Random,
    operations: list[str] | None = None,
    min_operations: int = 1,
    max_operations: int = 3,
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    """Apply selected or sampled degradations to an OpenCV BGR image."""

    if image is None or image.size == 0:
        raise ValueError("image must be a non-empty OpenCV image")
    operation_names = operations or choose_degradations(rng, min_operations, max_operations)
    result = image.copy()
    specs: list[dict[str, Any]] = []
    for operation in operation_names:
        result, spec = _apply_operation(result, operation, rng)
        specs.append(spec)
    return result, specs


def degrade_manifest(
    input_dir: Path = DEFAULT_INPUT_DIR,
    input_manifest: Path = DEFAULT_INPUT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_manifest: Path = DEFAULT_OUTPUT_MANIFEST,
    fraction: float = 0.5,
    seed: int = 42,
    min_operations: int = 1,
    max_operations: int = 3,
) -> list[dict[str, Any]]:
    """Degrade a reproducible fraction of images and write an analysis manifest."""

    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be between 0 and 1")
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    records = _load_manifest(Path(input_manifest))
    if not records:
        records = [
            {
                "doc_id": image_path.stem,
                "source": "synthetic",
                "file": _relative_path(image_path),
                "image_file": _relative_path(image_path),
                "ground_truth": {},
            }
            for image_path in sorted(input_dir.glob("*.png"))
        ]
    if not records:
        raise FileNotFoundError(f"No image records found in {input_dir}")

    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_records: list[dict[str, Any]] = []
    for record in records:
        source_value = record.get("image_file") or record.get("file")
        if not source_value:
            log.warning("Skipping %s because it has no image_file or file", record.get("doc_id"))
            continue
        source_path = _resolve_source_path(source_value, input_dir)
        image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"Could not read image: {source_path}")

        should_degrade = rng.random() < fraction
        degraded_specs: list[dict[str, Any]] = []
        if should_degrade:
            output_image, degraded_specs = degrade_image(
                image,
                rng,
                min_operations=min_operations,
                max_operations=max_operations,
            )
            destination = output_dir / f"{record['doc_id']}_degraded.png"
            if not cv2.imwrite(str(destination), output_image):
                raise RuntimeError(f"Could not write degraded image: {destination}")
            selected_file = _relative_path(destination)
        else:
            destination = output_dir / f"{record['doc_id']}_original.png"
            shutil.copyfile(source_path, destination)
            selected_file = _relative_path(destination)

        output_record = dict(record)
        output_record.update(
            {
                "source_file": _relative_path(source_path),
                "file": selected_file,
                "image_file": selected_file,
                "degraded": should_degrade,
                "degradations": degraded_specs,
                "degradation_types": [item["type"] for item in degraded_specs],
            }
        )
        result_records.append(output_record)

    _write_jsonl(output_manifest, result_records)
    log.info("Wrote %d image records to %s", len(result_records), output_manifest)
    return result_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--input-manifest", type=Path, default=DEFAULT_INPUT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument(
        "--fraction", type=float, default=0.5, help="Fraction to degrade (default: 0.5)"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-operations", type=int, default=1)
    parser.add_argument("--max-operations", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args()
    degrade_manifest(
        input_dir=args.input_dir,
        input_manifest=args.input_manifest,
        output_dir=args.output_dir,
        output_manifest=args.manifest,
        fraction=args.fraction,
        seed=args.seed,
        min_operations=args.min_operations,
        max_operations=args.max_operations,
    )


if __name__ == "__main__":
    main()
