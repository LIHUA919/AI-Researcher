from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


MINIMUM_SAMPLES = 1024
EXPECTED_DATASET = "cifar10"
EXPECTED_SPLIT = "test"
EXPECTED_EPOCHS = 2
CANONICAL_CIFAR10_TEST_PREFIX_SHA256 = (
    "184c368bb18c9a218c5d893d5153c76fb680f9546a5e054cf182233b19864089"
)


def _invalid(*codes: str) -> dict[str, Any]:
    return {
        "metrics": {},
        "repetitions": 1,
        "failed_repetitions": 1,
        "violations": [f"evidence_invalid:{code}" for code in codes],
    }


def _load_manifest(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, ["manifest_missing_or_invalid"]
    if not isinstance(payload, dict):
        return None, ["manifest_not_mapping"]
    return payload, []


def _load_arrays(path: Path) -> tuple[dict[str, np.ndarray] | None, list[str]]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            required = {
                "original_images",
                "reconstructed_images",
                "codebook_indices",
            }
            missing = sorted(required - set(archive.files))
            if missing:
                return None, [f"missing_array:{name}" for name in missing]
            return {name: archive[name] for name in required}, []
    except (OSError, ValueError):
        return None, ["arrays_missing_or_invalid"]


def evaluate_attempt(
    attempt_dir: str | Path,
    *,
    expected_originals_sha256: str | None = None,
    expected_codebook_size: int | None = None,
    expected_train_sample_count: int | None = None,
    expected_latent_dim: int | None = None,
) -> dict[str, Any]:
    """Compute smoke metrics from raw VQ evidence, never reported metrics."""

    root = Path(attempt_dir)
    manifest, violations = _load_manifest(root / "evaluation_manifest.json")
    arrays, array_violations = _load_arrays(root / "evaluation_arrays.npz")
    violations.extend(array_violations)
    if manifest is None or arrays is None:
        return _invalid(*violations)

    if manifest.get("schema_version") != 1:
        violations.append("unsupported_schema_version")
    if manifest.get("dataset_id") != EXPECTED_DATASET:
        violations.append("dataset_not_cifar10")
    if manifest.get("split") != EXPECTED_SPLIT:
        violations.append("split_not_test")
    if manifest.get("epochs_completed") != EXPECTED_EPOCHS:
        violations.append("epochs_not_two")
    seed = manifest.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        violations.append("seed_not_integer")

    sample_count = manifest.get("sample_count")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int):
        violations.append("sample_count_not_integer")
        sample_count = -1
    elif sample_count < MINIMUM_SAMPLES:
        violations.append("insufficient_samples")

    codebook_size = manifest.get("codebook_size")
    if (
        isinstance(codebook_size, bool)
        or not isinstance(codebook_size, int)
        or codebook_size < 2
    ):
        violations.append("invalid_codebook_size")
        codebook_size = -1
    elif (
        expected_codebook_size is not None
        and codebook_size != expected_codebook_size
    ):
        violations.append("codebook_size_mismatch")

    if (
        expected_train_sample_count is not None
        and manifest.get("train_sample_count") != expected_train_sample_count
    ):
        violations.append("train_sample_count_mismatch")
    if (
        expected_latent_dim is not None
        and manifest.get("latent_dim") != expected_latent_dim
    ):
        violations.append("latent_dim_mismatch")

    originals = arrays["original_images"]
    reconstructions = arrays["reconstructed_images"]
    indices = arrays["codebook_indices"]
    if originals.dtype != np.uint8 or reconstructions.dtype != np.uint8:
        violations.append("image_dtype_not_uint8")
    if originals.ndim != 4 or reconstructions.ndim != 4:
        violations.append("images_not_rank_four")
    elif originals.shape != reconstructions.shape:
        violations.append("image_shape_mismatch")
    else:
        if originals.shape[0] != sample_count:
            violations.append("sample_count_mismatch")
        if originals.shape[-1] not in {1, 3} and originals.shape[1] not in {1, 3}:
            violations.append("image_channel_dimension_invalid")

    if not np.issubdtype(indices.dtype, np.integer):
        violations.append("indices_not_integer")
    if indices.ndim < 1 or indices.size == 0:
        violations.append("indices_empty")
    elif indices.shape[0] != sample_count:
        violations.append("index_sample_count_mismatch")
    elif codebook_size > 0 and (
        int(indices.min()) < 0 or int(indices.max()) >= codebook_size
    ):
        violations.append("index_out_of_range")

    if violations:
        return _invalid(*violations)

    if expected_originals_sha256 is not None:
        originals_digest = hashlib.sha256(
            originals[:MINIMUM_SAMPLES].tobytes()
        ).hexdigest()
        if originals_digest != expected_originals_sha256:
            return _invalid("cifar10_test_prefix_digest_mismatch")

    originals_float = originals.astype(np.float64) / 255.0
    reconstructions_float = reconstructions.astype(np.float64) / 255.0
    reconstruction_mse = float(
        np.mean(np.square(originals_float - reconstructions_float))
    )
    psnr_denominator = max(reconstruction_mse, np.finfo(np.float64).eps)
    reconstruction_psnr_db = 10.0 * math.log10(1.0 / psnr_denominator)

    counts = np.bincount(indices.reshape(-1), minlength=codebook_size)
    active_counts = counts[counts > 0]
    probabilities = active_counts.astype(np.float64) / float(indices.size)
    codebook_perplexity = float(
        np.exp(-np.sum(probabilities * np.log(probabilities)))
    )
    active_codes = int(active_counts.size)
    return {
        "metrics": {
            "codebook_utilization": active_codes / codebook_size,
            "active_codes": active_codes,
            "codebook_perplexity": codebook_perplexity,
            "reconstruction_mse": reconstruction_mse,
            "reconstruction_psnr_db": reconstruction_psnr_db,
        },
        "repetitions": 1,
        "failed_repetitions": 0,
        "violations": [],
    }


def main(
    attempt_dir: str,
    *,
    expected_codebook_size: int | None = None,
    expected_train_sample_count: int | None = None,
    expected_latent_dim: int | None = None,
) -> int:
    root = Path(attempt_dir)
    result = evaluate_attempt(
        root,
        expected_originals_sha256=CANONICAL_CIFAR10_TEST_PREFIX_SHA256,
        expected_codebook_size=expected_codebook_size,
        expected_train_sample_count=expected_train_sample_count,
        expected_latent_dim=expected_latent_dim,
    )
    (root / "verification_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_dir")
    parser.add_argument("--expected-codebook-size", type=int)
    parser.add_argument("--expected-train-sample-count", type=int)
    parser.add_argument("--expected-latent-dim", type=int)
    cli_args = parser.parse_args()
    raise SystemExit(
        main(
            cli_args.attempt_dir,
            expected_codebook_size=cli_args.expected_codebook_size,
            expected_train_sample_count=cli_args.expected_train_sample_count,
            expected_latent_dim=cli_args.expected_latent_dim,
        )
    )
