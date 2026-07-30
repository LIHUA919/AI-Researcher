from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import yaml

from benchmark.evaluators.one_layer_vq_smoke.evaluate_v3 import (
    evaluate_attempt_v3,
)
from benchmark.evaluators.one_layer_vq_smoke.provenance_schema import (
    canonical_json_bytes,
    content_digest,
    evaluator_identity,
    evidence_payload_digest,
    file_set_digest,
    semantic_digest,
)
from benchmark.real_smoke.one_layer_vq.train import (
    build_evaluation_manifest,
    evidence_payload_digest as training_evidence_payload_digest,
)
from research_agent.inno.experience import (
    evaluator_identity as runtime_evaluator_identity,
    load_evaluation_contract,
)
from research_agent.runtime.trial_provenance import (
    content_digest as runtime_content_digest,
    evidence_payload_digest as runtime_evidence_payload_digest,
    file_set_digest as runtime_file_set_digest,
)


EVALUATOR_DIR = (
    Path(__file__).resolve().parents[2] / "benchmark/evaluators/one_layer_vq_smoke"
)
CONTRACT_PATH = EVALUATOR_DIR / "contract.closed_loop_v3.yaml"


def _write_valid_v3_evidence(root: Path) -> None:
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    policy = contract["adaptive_experiment"]
    effective_config = {
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
        "digest": semantic_digest(
            "ai-researcher/proposal/v1",
            proposal_record,
        ),
        "record": proposal_record,
        "change": {
            "name": "projection_lr_multiplier",
            "from": 1.0,
            "to": 2.0,
        },
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
    provenance = {
        "intervention_digest": semantic_digest(
            "ai-researcher/intervention/v1",
            {
                "commitment_weight": 0.25,
                "projection_lr_multiplier": 2.0,
            },
        ),
        "config_digest": semantic_digest(
            "ai-researcher/run-config/v1",
            effective_config,
        ),
        "source_digest": policy["expected_source_digest"],
        "dataset_digest": semantic_digest(
            "ai-researcher/dataset-plan/v1",
            descriptors["dataset"],
        ),
        "environment_digest": semantic_digest(
            "ai-researcher/environment/v1",
            descriptors["environment"],
        ),
        "contract_digest": content_digest(
            "ai-researcher/contract/v1",
            CONTRACT_PATH.read_bytes(),
        ),
        "evaluator_digest": evaluator_identity(contract, EVALUATOR_DIR),
        "manipulation_status": "changed",
    }
    spec = {
        "schema_version": 1,
        "attempt_key": "seed-401:treatment:iteration-002",
        "task_id": contract["task_id"],
        "policy": {"id": policy["policy_id"], "version": policy["version"]},
        "proposal": proposal,
        "effective_config": effective_config,
        "descriptors": descriptors,
        "provenance": provenance,
        "required_artifacts": contract["required_artifacts"],
    }
    root.mkdir(parents=True, exist_ok=True)
    spec_path = root / "attempt_spec.json"
    spec_path.write_bytes(canonical_json_bytes(spec))
    spec_sha256 = hashlib.sha256(spec_path.read_bytes()).hexdigest()

    sample_count = 1024
    originals = np.zeros((sample_count, 1, 1, 3), dtype=np.uint8)
    reconstructions = np.full_like(originals, 10)
    indices = np.resize(
        np.array([0, 1, 1, 3], dtype=np.int32),
        sample_count,
    )
    arrays = {
        "original_images": originals,
        "reconstructed_images": reconstructions,
        "codebook_indices": indices,
    }
    np.savez_compressed(root / "evaluation_arrays.npz", **arrays)
    payload_digest = evidence_payload_digest(arrays)
    legacy_digest = hashlib.sha256(
        originals.tobytes() + reconstructions.tobytes() + indices.tobytes()
    ).hexdigest()
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
        _attempt_spec_sha256=spec_sha256,
        _attempt_spec_payload=spec,
    )
    manifest = build_evaluation_manifest(
        args=args,
        repository_root=Path(__file__).resolve().parents[2],
        resolved_device="cpu",
        evidence_payload_sha256=payload_digest,
        legacy_evidence_sha256=legacy_digest,
        originals_sha256=hashlib.sha256(originals[:1024].tobytes()).hexdigest(),
        started_at="2026-07-30T00:00:00+00:00",
        completed_at="2026-07-30T00:01:00+00:00",
    )
    (root / "evaluation_manifest.json").write_bytes(canonical_json_bytes(manifest))
    (root / "run.log").write_text("completed\n", encoding="utf-8")


def test_v3_evaluator_accepts_independently_recomputable_evidence(tmp_path):
    _write_valid_v3_evidence(tmp_path)

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 0
    assert result["violations"] == []
    assert result["metrics"]["active_codes"] == 3
    assert result["metrics"]["codebook_utilization"] == 3 / 128


def test_v3_evaluator_rejects_manifest_config_claim_that_was_not_executed(
    tmp_path,
):
    _write_valid_v3_evidence(tmp_path)
    manifest_path = tmp_path / "evaluation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["effective_config"]["projection_lr_multiplier"] = 4.0
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert result["metrics"] == {}
    assert "evidence_invalid:manifest_effective_config_mismatch" in result["violations"]


def test_v3_evaluator_rejects_raw_array_bytes_not_bound_to_manifest(tmp_path):
    _write_valid_v3_evidence(tmp_path)
    arrays_path = tmp_path / "evaluation_arrays.npz"
    with np.load(arrays_path, allow_pickle=False) as archive:
        arrays = {name: archive[name] for name in archive.files}
    arrays["reconstructed_images"] = arrays["reconstructed_images"].copy()
    arrays["reconstructed_images"][0, 0, 0, 0] = 11
    np.savez_compressed(arrays_path, **arrays)

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert "evidence_invalid:evidence_payload_digest_mismatch" in result["violations"]


def test_v3_evaluator_rejects_self_consistent_unpinned_source_claim(tmp_path):
    _write_valid_v3_evidence(tmp_path)
    spec_path = tmp_path / "attempt_spec.json"
    manifest_path = tmp_path / "evaluation_manifest.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    forged = "f" * 64
    spec["provenance"]["source_digest"] = forged
    manifest["provenance"]["source_digest"] = forged
    spec_path.write_bytes(canonical_json_bytes(spec))
    manifest["attempt_spec_sha256"] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert "evidence_invalid:source_digest_mismatch" in result["violations"]


def test_v3_evaluator_binds_full_proposal_record_including_rationale(tmp_path):
    _write_valid_v3_evidence(tmp_path)
    spec_path = tmp_path / "attempt_spec.json"
    manifest_path = tmp_path / "evaluation_manifest.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec["proposal"]["record"]["rationale"] = "tampered rationale"
    spec_path.write_bytes(canonical_json_bytes(spec))
    manifest["attempt_spec_sha256"] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert "evidence_invalid:proposal_digest_mismatch" in result["violations"]


def test_v3_evaluator_rejects_rehashed_nonofficial_dataset_descriptor(
    tmp_path,
):
    _write_valid_v3_evidence(tmp_path)
    spec_path = tmp_path / "attempt_spec.json"
    manifest_path = tmp_path / "evaluation_manifest.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dataset = spec["descriptors"]["dataset"]
    dataset["archive_sha256"] = "f" * 64
    forged_digest = semantic_digest(
        "ai-researcher/dataset-plan/v1",
        dataset,
    )
    spec["provenance"]["dataset_digest"] = forged_digest
    manifest["descriptors"] = spec["descriptors"]
    manifest["provenance"]["dataset_digest"] = forged_digest
    spec_path.write_bytes(canonical_json_bytes(spec))
    manifest["attempt_spec_sha256"] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert "evidence_invalid:dataset_descriptor_mismatch" in (result["violations"])


def test_v3_evaluator_rejects_rehashed_environment_config_mismatch(tmp_path):
    _write_valid_v3_evidence(tmp_path)
    spec_path = tmp_path / "attempt_spec.json"
    manifest_path = tmp_path / "evaluation_manifest.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    environment = spec["descriptors"]["environment"]
    environment["resolved_device"] = "mps"
    forged_digest = semantic_digest(
        "ai-researcher/environment/v1",
        environment,
    )
    spec["provenance"]["environment_digest"] = forged_digest
    manifest["descriptors"] = spec["descriptors"]
    manifest["provenance"]["environment_digest"] = forged_digest
    spec_path.write_bytes(canonical_json_bytes(spec))
    manifest["attempt_spec_sha256"] = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    result = evaluate_attempt_v3(
        tmp_path,
        contract_path=CONTRACT_PATH,
        expected_originals_sha256=None,
    )

    assert result["failed_repetitions"] == 1
    assert (
        "evidence_invalid:environment_descriptor_config_mismatch"
        in (result["violations"])
    )


def test_v3_contract_pins_the_exact_frozen_source_set():
    contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    repo_root = Path(__file__).resolve().parents[2]
    sources = {
        "protocol.py": (repo_root / "benchmark/real_smoke/one_layer_vq/train.py"),
        "run_training_testing.py": (
            repo_root
            / "benchmark/process/dataset_candidate/vq"
            / "run_training_testing.py"
        ),
        "attempt_spec.py": (
            repo_root / "benchmark/process/dataset_candidate/vq" / "attempt_spec.py"
        ),
    }
    actual = file_set_digest("ai-researcher/source-set/v1", sources)

    assert contract["adaptive_experiment"]["expected_source_digest"] == actual
    assert runtime_file_set_digest("ai-researcher/source-set/v1", sources) == actual


def test_v3_external_and_runtime_evaluator_identity_match():
    raw_contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract = load_evaluation_contract(CONTRACT_PATH)

    assert evaluator_identity(raw_contract, EVALUATOR_DIR) == (
        runtime_evaluator_identity(contract, EVALUATOR_DIR)
    )
    assert content_digest(
        "ai-researcher/contract/v1",
        CONTRACT_PATH.read_bytes(),
    ) == runtime_content_digest(
        "ai-researcher/contract/v1",
        CONTRACT_PATH.read_bytes(),
    )


def test_v3_all_evidence_payload_digest_implementations_match():
    arrays = {
        "original_images": np.zeros((2, 1, 1, 3), dtype=np.uint8),
        "reconstructed_images": np.ones((2, 1, 1, 3), dtype=np.uint8),
        "codebook_indices": np.array([0, 1], dtype=np.int32),
    }

    external = evidence_payload_digest(arrays)

    assert training_evidence_payload_digest(arrays) == external
    assert runtime_evidence_payload_digest(arrays) == external
