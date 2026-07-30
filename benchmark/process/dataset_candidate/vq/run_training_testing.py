"""Default entrypoint for the frozen two-epoch CIFAR-10 SimVQ protocol."""

from __future__ import annotations

import os
from pathlib import Path
import sys

try:
    from attempt_spec import (
        SPEC_PATH_ENV,
        SPEC_SHA256_ENV,
        LoadedAttemptSpec,
        load_attempt_spec_from_environment,
    )
except ModuleNotFoundError:
    from benchmark.process.dataset_candidate.vq.attempt_spec import (
        SPEC_PATH_ENV,
        SPEC_SHA256_ENV,
        LoadedAttemptSpec,
        load_attempt_spec_from_environment,
    )
from protocol import build_parser, run


def _legacy_v2_default_arguments() -> list[str]:
    project_dir = Path(__file__).resolve().parent
    seed = (
        (project_dir / ".experiment_seed")
        .read_text(
            encoding="utf-8",
        )
        .strip()
    )
    return [
        "--output-dir",
        str(project_dir),
        "--data-dir",
        str(project_dir / "data"),
        "--data-source",
        "torchvision",
        "--device",
        "auto",
        "--seed",
        seed,
        "--epochs",
        "2",
        "--train-samples",
        "8192",
        "--test-samples",
        "1024",
        "--batch-size",
        "128",
        "--codebook-size",
        "128",
        "--latent-dim",
        "16",
        "--variant",
        "simvq",
        "--overwrite",
    ]


def _v3_arguments(spec: LoadedAttemptSpec) -> list[str]:
    project_dir = Path(__file__).resolve().parent
    config = spec.payload["effective_config"]
    assert isinstance(config, dict)
    return [
        "--output-dir",
        str(spec.output_dir),
        "--data-dir",
        str(project_dir / "data"),
        "--data-source",
        str(config["data_source"]),
        "--device",
        str(config["resolved_device"]),
        "--seed",
        str(config["seed"]),
        "--epochs",
        str(config["epochs"]),
        "--train-samples",
        str(config["train_samples"]),
        "--test-samples",
        str(config["test_samples"]),
        "--batch-size",
        str(config["batch_size"]),
        "--codebook-size",
        str(config["codebook_size"]),
        "--latent-dim",
        str(config["latent_dim"]),
        "--variant",
        str(config["quantizer_variant"]),
        "--commitment-weight",
        str(config["commitment_weight"]),
        "--learning-rate",
        str(config["base_learning_rate"]),
        "--projection-lr-multiplier",
        str(config["projection_lr_multiplier"]),
    ]


# Kept for callers and tests that reproduce the V2 frozen entrypoint.
_default_arguments = _legacy_v2_default_arguments


def main() -> int:
    parser = build_parser()
    v3_requested = bool(
        os.environ.get(SPEC_PATH_ENV) or os.environ.get(SPEC_SHA256_ENV)
    )
    loaded_spec = None
    if v3_requested:
        loaded_spec = load_attempt_spec_from_environment()
        arguments = _v3_arguments(loaded_spec)
    elif not sys.argv[1:]:
        arguments = _legacy_v2_default_arguments()
    else:
        arguments = sys.argv[1:]
    parsed = parser.parse_args(arguments)
    if loaded_spec is not None:
        parsed._attempt_spec_payload = loaded_spec.payload
        parsed._attempt_spec_sha256 = loaded_spec.sha256
    run(parsed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
