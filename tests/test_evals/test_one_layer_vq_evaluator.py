from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from benchmark.evaluators.one_layer_vq_smoke.evaluate import evaluate_attempt, main
from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    Observation,
    load_evaluation_contract,
)


def write_evidence(
    root: Path,
    *,
    codebook_indices: np.ndarray | None = None,
    originals: np.ndarray | None = None,
    reconstructions: np.ndarray | None = None,
    manifest_updates: dict | None = None,
) -> None:
    sample_count = 1024
    if originals is None:
        originals = np.zeros((sample_count, 1, 1, 3), dtype=np.uint8)
    if reconstructions is None:
        reconstructions = np.full_like(originals, 10)
    if codebook_indices is None:
        codebook_indices = np.resize(
            np.array([0, 1, 1, 3], dtype=np.int32),
            sample_count,
        )
    np.savez_compressed(
        root / "evaluation_arrays.npz",
        original_images=originals,
        reconstructed_images=reconstructions,
        codebook_indices=codebook_indices,
    )
    manifest = {
        "schema_version": 1,
        "dataset_id": "cifar10",
        "split": "test",
        "epochs_completed": 2,
        "seed": 0,
        "codebook_size": 8,
        "sample_count": sample_count,
    }
    manifest.update(manifest_updates or {})
    (root / "evaluation_manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "run.log").write_text("training completed\n", encoding="utf-8")


def test_evaluator_computes_metrics_from_raw_arrays(tmp_path):
    write_evidence(tmp_path)

    result = evaluate_attempt(tmp_path)

    expected_mse = (10 / 255) ** 2
    assert result["metrics"]["codebook_utilization"] == 3 / 8
    assert result["metrics"]["active_codes"] == 3
    assert result["metrics"]["reconstruction_mse"] == expected_mse
    assert result["metrics"]["reconstruction_psnr_db"] == 10 * math.log10(
        1 / expected_mse
    )
    assert result["metrics"]["codebook_perplexity"] > 2
    assert result["repetitions"] == 1
    assert result["failed_repetitions"] == 0
    assert result["violations"] == []


def test_evaluator_rejects_out_of_range_indices(tmp_path):
    indices = np.zeros(1024, dtype=np.int32)
    indices[-1] = 8
    write_evidence(tmp_path, codebook_indices=indices)

    exit_code = main(str(tmp_path))
    result = json.loads(
        (tmp_path / "verification_result.json").read_text(encoding="utf-8")
    )

    assert exit_code == 0
    assert result["failed_repetitions"] == 1
    assert result["metrics"] == {}
    assert result["violations"] == ["evidence_invalid:index_out_of_range"]


def test_evaluator_rejects_claimed_sample_count_and_float_images(tmp_path):
    originals = np.zeros((1024, 1, 1, 3), dtype=np.float32)
    write_evidence(
        tmp_path,
        originals=originals,
        reconstructions=originals.copy(),
        manifest_updates={"sample_count": 2048},
    )

    result = evaluate_attempt(tmp_path)

    assert result["failed_repetitions"] == 1
    assert result["metrics"] == {}
    assert set(result["violations"]) == {
        "evidence_invalid:image_dtype_not_uint8",
        "evidence_invalid:index_sample_count_mismatch",
        "evidence_invalid:sample_count_mismatch",
    }


def test_evaluator_rejects_too_few_samples_and_wrong_protocol(tmp_path):
    originals = np.zeros((32, 1, 1, 3), dtype=np.uint8)
    write_evidence(
        tmp_path,
        originals=originals,
        reconstructions=originals.copy(),
        codebook_indices=np.zeros(32, dtype=np.int32),
        manifest_updates={
            "dataset_id": "synthetic",
            "epochs_completed": 1,
            "sample_count": 32,
        },
    )

    result = evaluate_attempt(tmp_path)

    assert result["failed_repetitions"] == 1
    assert set(result["violations"]) == {
        "evidence_invalid:dataset_not_cifar10",
        "evidence_invalid:epochs_not_two",
        "evidence_invalid:insufficient_samples",
    }


def test_evaluator_enforces_frozen_closed_loop_configuration(tmp_path):
    write_evidence(
        tmp_path,
        manifest_updates={
            "train_sample_count": 4096,
            "latent_dim": 8,
        },
    )

    result = evaluate_attempt(
        tmp_path,
        expected_codebook_size=128,
        expected_train_sample_count=8192,
        expected_latent_dim=16,
    )

    assert result["failed_repetitions"] == 1
    assert set(result["violations"]) == {
        "evidence_invalid:codebook_size_mismatch",
        "evidence_invalid:latent_dim_mismatch",
        "evidence_invalid:train_sample_count_mismatch",
    }


def test_repository_contract_rejects_noncanonical_cifar_images(tmp_path):
    write_evidence(tmp_path)
    evaluator_dir = (
        Path(__file__).resolve().parents[2]
        / "benchmark"
        / "evaluators"
        / "one_layer_vq_smoke"
    )
    contract = load_evaluation_contract(evaluator_dir / "contract.yaml")
    refs = []
    for name in contract.required_artifacts:
        path = tmp_path / name
        content = path.read_bytes()
        refs.append(
            ArtifactRef(
                path=str(path),
                sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        )
    now = datetime.now(timezone.utc)
    observation = Observation(
        observation_id="raw-evidence",
        attempt_id="attempt-1",
        exit_code=0,
        metrics={"codebook_utilization": 1.0},
        artifact_refs=refs,
        started_at=now,
        completed_at=now,
        environment_fingerprint="test",
    )

    verification = CommandVerifier(contract_dir=evaluator_dir).verify(
        contract,
        observation,
    )

    assert verification.valid is False
    assert verification.passed is False
    assert verification.verified_metrics == {}
    assert "evidence_invalid:cifar10_test_prefix_digest_mismatch" in (
        verification.violations
    )
    assert Path(verification.evidence_refs[-1].path).name == (
        "verification_result.json"
    )
