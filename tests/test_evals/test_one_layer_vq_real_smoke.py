import hashlib
import importlib.metadata
import numpy as np
import platform
import pytest
import torch
from types import SimpleNamespace

from benchmark.real_smoke.one_layer_vq.train import (
    SimVQAutoencoder,
    SimVQQuantizer,
    VanillaVQQuantizer,
    build_evaluation_manifest,
    build_optimizer,
    evidence_payload_digest,
    validate_v3_execution_descriptors,
)


def test_simvq_quantizer_freezes_basis_and_trains_linear_projection():
    quantizer = SimVQQuantizer(codebook_size=16, latent_dim=8, commitment_weight=0.25)

    assert quantizer.code_basis.weight.requires_grad is False
    assert quantizer.code_projection.weight.requires_grad is True
    assert torch.allclose(
        quantizer.code_projection.weight,
        torch.eye(8),
    )


def test_simvq_smoke_model_returns_reconstruction_indices_and_finite_loss():
    model = SimVQAutoencoder(
        codebook_size=16,
        latent_dim=8,
        commitment_weight=0.25,
    )
    images = torch.rand(4, 3, 32, 32)

    reconstructions, indices, quantization_loss = model(images)

    assert reconstructions.shape == images.shape
    assert indices.shape == (4, 8, 8)
    assert indices.dtype == torch.int64
    assert int(indices.min()) >= 0
    assert int(indices.max()) < 16
    assert torch.isfinite(quantization_loss)


def test_vanilla_quantizer_trains_codebook_without_linear_projection():
    quantizer = VanillaVQQuantizer(
        codebook_size=16,
        latent_dim=8,
        commitment_weight=0.25,
    )

    assert quantizer.codebook.weight.requires_grad is True
    assert not hasattr(quantizer, "code_projection")


def test_autoencoder_rejects_unknown_quantizer_variant():
    try:
        SimVQAutoencoder(
            codebook_size=16,
            latent_dim=8,
            commitment_weight=0.25,
            variant="unknown",
        )
    except ValueError as exc:
        assert "unknown quantizer variant" in str(exc)
    else:
        raise AssertionError("unknown quantizer variant was accepted")


def test_projection_lr_multiplier_only_changes_projection_optimizer_group():
    model = SimVQAutoencoder(
        codebook_size=16,
        latent_dim=8,
        commitment_weight=0.25,
    )

    optimizer = build_optimizer(
        model,
        learning_rate=0.0003,
        projection_lr_multiplier=2.0,
    )

    groups = {group["name"]: group for group in optimizer.param_groups}
    assert groups["base"]["lr"] == 0.0003
    assert groups["code_projection"]["lr"] == 0.0006
    projection_ids = {
        id(parameter) for parameter in model.quantizer.code_projection.parameters()
    }
    assert {
        id(parameter) for parameter in groups["code_projection"]["params"]
    } == projection_ids
    assert not (
        {id(parameter) for parameter in groups["base"]["params"]} & projection_ids
    )
    optimizer_ids = [
        id(parameter)
        for group in optimizer.param_groups
        for parameter in group["params"]
    ]
    expected_ids = [
        id(parameter) for parameter in model.parameters() if parameter.requires_grad
    ]
    assert sorted(optimizer_ids) == sorted(expected_ids)


def test_commitment_weight_changes_the_quantization_loss():
    low_weight = SimVQQuantizer(
        codebook_size=16,
        latent_dim=8,
        commitment_weight=0.1,
    )
    high_weight = SimVQQuantizer(
        codebook_size=16,
        latent_dim=8,
        commitment_weight=1.0,
    )
    high_weight.load_state_dict(low_weight.state_dict())
    latents = torch.linspace(-1.0, 1.0, steps=4 * 8 * 2 * 2).reshape(
        4,
        8,
        2,
        2,
    )

    _, low_indices, low_loss = low_weight(latents)
    _, high_indices, high_loss = high_weight(latents)

    assert torch.equal(low_indices, high_indices)
    assert high_loss > low_loss


def test_evidence_payload_digest_frames_name_dtype_shape_and_bytes():
    base = {
        "original_images": np.zeros((2, 1, 1, 3), dtype=np.uint8),
    }
    base_digest = evidence_payload_digest(base)

    assert evidence_payload_digest({"renamed": base["original_images"]}) != base_digest
    assert (
        evidence_payload_digest(
            {"original_images": base["original_images"].astype(np.int8)}
        )
        != base_digest
    )
    assert (
        evidence_payload_digest(
            {"original_images": base["original_images"].reshape(1, 2, 1, 3)}
        )
        != base_digest
    )
    changed = base["original_images"].copy()
    changed[0, 0, 0, 0] = 1
    assert evidence_payload_digest({"original_images": changed}) != base_digest


def test_v3_manifest_echoes_verified_config_intervention_and_provenance(
    tmp_path,
):
    config = {
        "dataset_id": "cifar10",
        "data_source": "torchvision",
        "train_split": "train",
        "test_split": "test",
        "epochs": 2,
        "train_samples": 8192,
        "test_samples": 1024,
        "batch_size": 128,
        "codebook_size": 128,
        "latent_dim": 16,
        "quantizer_variant": "simvq",
        "base_learning_rate": 0.0003,
        "device_policy": "auto",
        "projection_lr_multiplier": 2.0,
        "commitment_weight": 0.25,
        "seed": 401,
        "resolved_device": "cpu",
    }
    proposal_record = {
        "schema_version": "1",
        "domain": "vq",
        "schema_id": "vq.intervention/v1",
        "decision_point": "vq.quantizer_optimization",
        "knob": "projection_lr_multiplier",
        "target": 2.0,
        "cited_knowledge_ids": ["knowledge:projection"],
        "expected_primary_metric_direction": "increase",
        "guardrail_risks": [],
        "rationale": "Test projection-specific learning rate.",
    }
    proposal = {
        "digest": "a" * 64,
        "record": proposal_record,
        "change": {
            "name": "projection_lr_multiplier",
            "from": 1.0,
            "to": 2.0,
        },
    }
    provenance = {
        "intervention_digest": "b" * 64,
        "config_digest": "c" * 64,
        "source_digest": "d" * 64,
        "dataset_digest": "e" * 64,
        "environment_digest": "f" * 64,
        "contract_digest": "1" * 64,
        "evaluator_digest": "2" * 64,
        "manipulation_status": "changed",
    }
    descriptors = {
        "dataset": {
            "dataset_id": "cifar10",
            "archive_sha256": (
                "6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce"
            ),
            "source": "torchvision",
            "train_split": "train",
            "test_split": "test",
            "train_selector": {
                "name": "torch_randperm_without_replacement",
                "version": "1",
                "seed": 401,
                "count": 8192,
            },
            "test_selector": {
                "name": "canonical_prefix",
                "version": "1",
                "count": 1024,
            },
            "transform": {
                "name": "torchvision.transforms.ToTensor",
                "version": "1",
            },
        },
        "environment": {
            "python": "3.11.9",
            "numpy": "2.0.0",
            "torch": "2.7.0",
            "torchvision": "0.22.0",
            "platform_system": "Darwin",
            "platform_machine": "arm64",
            "requested_device": "auto",
            "resolved_device": "cpu",
        },
    }
    args = SimpleNamespace(
        data_source="torchvision",
        epochs=2,
        seed=401,
        codebook_size=128,
        test_samples=1024,
        train_samples=8192,
        variant="simvq",
        latent_dim=16,
        commitment_weight=0.25,
        learning_rate=0.0003,
        batch_size=128,
        projection_lr_multiplier=2.0,
        _attempt_spec_sha256="3" * 64,
        _attempt_spec_payload={
            "schema_version": 1,
            "attempt_key": "seed-401:treatment:iteration-002",
            "task_id": "one_layer_vq:task1",
            "policy": {"id": "one-layer-vq-phase-a", "version": "1"},
            "proposal": proposal,
            "effective_config": config,
            "descriptors": descriptors,
            "provenance": provenance,
            "required_artifacts": [
                "attempt_spec.json",
                "evaluation_manifest.json",
                "evaluation_arrays.npz",
                "run.log",
            ],
        },
    )

    manifest = build_evaluation_manifest(
        args=args,
        repository_root=tmp_path,
        resolved_device="cpu",
        evidence_payload_sha256="4" * 64,
        legacy_evidence_sha256="5" * 64,
        originals_sha256="6" * 64,
        started_at="2026-07-30T00:00:00+00:00",
        completed_at="2026-07-30T00:01:00+00:00",
    )

    assert manifest["schema_version"] == 2
    assert manifest["attempt_spec_sha256"] == "3" * 64
    assert manifest["task_id"] == "one_layer_vq:task1"
    assert manifest["contract"] == {
        "id": "one-layer-vq-cifar10-adaptive",
        "version": "3-phase-a",
        "digest": "1" * 64,
    }
    assert manifest["provenance"]["proposal_digest"] == "a" * 64
    assert manifest["provenance"]["config_digest"] == "c" * 64
    assert manifest["intervention"]["effective_knobs"] == {
        "projection_lr_multiplier": 2.0,
        "commitment_weight": 0.25,
    }
    assert manifest["effective_config"]["base_learning_rate"] == 0.0003
    assert manifest["effective_config"]["resolved_device"] == "cpu"
    assert manifest["effective_config"] == config
    assert manifest["descriptors"] == descriptors
    assert manifest["optimizer"] == {
        "base_group": "base",
        "base_learning_rate": 0.0003,
        "projection_group": "code_projection",
        "projection_learning_rate": 0.0006,
    }
    assert manifest["execution"]["exit_code"] == 0
    assert manifest["evidence_payload_digest"] == "4" * 64


def test_manifest_defaults_to_legacy_schema_without_attempt_spec(tmp_path):
    args = SimpleNamespace(
        data_source="torchvision",
        epochs=2,
        seed=401,
        codebook_size=128,
        test_samples=1024,
        train_samples=8192,
        variant="simvq",
        latent_dim=16,
        commitment_weight=0.25,
        learning_rate=0.0003,
        batch_size=128,
        projection_lr_multiplier=1.0,
    )

    manifest = build_evaluation_manifest(
        args=args,
        repository_root=tmp_path,
        resolved_device="cpu",
        evidence_payload_sha256="4" * 64,
        legacy_evidence_sha256="5" * 64,
        originals_sha256="6" * 64,
    )

    assert manifest["schema_version"] == 1
    assert manifest["evidence_digest"] == "5" * 64
    assert "attempt_spec_sha256" not in manifest
    assert "evidence_payload_digest" not in manifest


def test_v3_execution_validates_actual_dataset_and_interpreter_descriptors(
    tmp_path,
):
    project = tmp_path / "workplace/project"
    project.mkdir(parents=True)
    archive = tmp_path / "workplace/dataset_candidate/cifar-10-python.tar.gz"
    archive.parent.mkdir()
    archive.write_bytes(b"test archive")
    config = {
        "dataset_id": "cifar10",
        "data_source": "torchvision",
        "train_split": "train",
        "test_split": "test",
        "epochs": 2,
        "train_samples": 8192,
        "test_samples": 1024,
        "batch_size": 128,
        "codebook_size": 128,
        "latent_dim": 16,
        "quantizer_variant": "simvq",
        "base_learning_rate": 0.0003,
        "device_policy": "auto",
        "projection_lr_multiplier": 1.0,
        "commitment_weight": 0.25,
        "seed": 401,
        "resolved_device": "cpu",
    }
    descriptors = {
        "dataset": {
            "dataset_id": "cifar10",
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "source": "torchvision",
            "train_split": "train",
            "test_split": "test",
            "train_selector": {
                "name": "torch_randperm_without_replacement",
                "version": "1",
                "seed": 401,
                "count": 8192,
            },
            "test_selector": {
                "name": "canonical_prefix",
                "version": "1",
                "count": 1024,
            },
            "transform": {
                "name": "torchvision.transforms.ToTensor",
                "version": "1",
            },
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": importlib.metadata.version("numpy"),
            "torch": importlib.metadata.version("torch"),
            "torchvision": importlib.metadata.version("torchvision"),
            "platform_system": platform.system(),
            "platform_machine": platform.machine(),
            "requested_device": "auto",
            "resolved_device": "cpu",
        },
    }
    args = SimpleNamespace(
        _attempt_spec_payload={
            "effective_config": config,
            "descriptors": descriptors,
        }
    )

    assert (
        validate_v3_execution_descriptors(
            args,
            project_dir=project,
            resolved_device="cpu",
        )
        == descriptors
    )

    descriptors["environment"]["python"] = "0.0.0"
    with pytest.raises(ValueError, match="dataset/environment"):
        validate_v3_execution_descriptors(
            args,
            project_dir=project,
            resolved_device="cpu",
        )
