from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from benchmark.evaluators.one_layer_vq_smoke.evaluate import (
    CANONICAL_CIFAR10_TEST_PREFIX_SHA256,
    evaluate_attempt,
)


METRIC_DIRECTIONS = {
    "codebook_utilization": "maximize",
    "codebook_perplexity": "maximize",
    "reconstruction_mse": "minimize",
    "reconstruction_psnr_db": "maximize",
}


def summarize_verified_metrics(
    verified: dict[int, dict[str, dict[str, float]]],
) -> dict[str, Any]:
    paired_deltas = []
    for seed in sorted(verified):
        variants = verified[seed]
        row: dict[str, float | int] = {"seed": seed}
        for metric, direction in METRIC_DIRECTIONS.items():
            vanilla = variants["vanilla"][metric]
            simvq = variants["simvq"][metric]
            delta = simvq - vanilla if direction == "maximize" else vanilla - simvq
            row[metric] = round(delta, 12)
        paired_deltas.append(row)

    variant_means = {}
    for variant in ("vanilla", "simvq"):
        variant_means[variant] = {
            metric: fmean(
                verified[seed][variant][metric] for seed in sorted(verified)
            )
            for metric in METRIC_DIRECTIONS
        }
    mean_paired_delta = {
        metric: round(
            fmean(float(row[metric]) for row in paired_deltas),
            12,
        )
        for metric in METRIC_DIRECTIONS
    }
    return {
        "variant_means": variant_means,
        "paired_deltas": paired_deltas,
        "mean_paired_delta": mean_paired_delta,
    }


def build_report(root: Path, seeds: list[int]) -> dict[str, Any]:
    verified: dict[int, dict[str, dict[str, float]]] = {}
    manifests = []
    for seed in seeds:
        verified[seed] = {}
        for variant in ("vanilla", "simvq"):
            attempt_dir = root / variant / f"seed-{seed}"
            result = evaluate_attempt(
                attempt_dir,
                expected_originals_sha256=(
                    CANONICAL_CIFAR10_TEST_PREFIX_SHA256
                ),
            )
            if result["failed_repetitions"] or result["violations"]:
                raise RuntimeError(
                    f"invalid evidence for {variant} seed {seed}: "
                    f"{result['violations']}"
                )
            verified[seed][variant] = result["metrics"]
            manifest = json.loads(
                (attempt_dir / "evaluation_manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            manifests.append(manifest)

    common_fields = (
        "batch_size",
        "codebook_size",
        "commitment_weight",
        "dataset_id",
        "dataset_source",
        "device",
        "epochs_completed",
        "latent_dim",
        "learning_rate",
        "sample_count",
        "source_sha256",
        "train_sample_count",
        "training_protocol",
    )
    common_configuration = {
        field: manifests[0][field] for field in common_fields
    }
    for manifest in manifests[1:]:
        candidate = {field: manifest[field] for field in common_fields}
        if candidate != common_configuration:
            raise RuntimeError("paired runs do not share one configuration")

    return {
        "schema_version": "1",
        "report_type": "real_data_method_smoke",
        "task_id": "one_layer_vq:task1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seeds": sorted(seeds),
        "configuration": common_configuration,
        "canonical_test_prefix_sha256": (
            CANONICAL_CIFAR10_TEST_PREFIX_SHA256
        ),
        "summary": summarize_verified_metrics(verified),
        "verified_metrics": {
            str(seed): verified[seed] for seed in sorted(verified)
        },
        "disclaimer": (
            "Real CIFAR-10 method smoke only. This is not an Experience Gain "
            "or paper-reproduction claim."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seeds", default="101,202,303")
    args = parser.parse_args()
    seeds = [int(value) for value in args.seeds.split(",") if value]
    report = build_report(args.root, seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
