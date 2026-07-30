from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml

try:
    from benchmark.evaluators.one_layer_vq_smoke.evaluate import (
        CANONICAL_CIFAR10_TEST_PREFIX_SHA256,
    )
    from benchmark.evaluators.one_layer_vq_smoke.provenance_schema import (
        content_digest,
        evaluator_identity,
        evidence_payload_digest,
        semantic_digest,
    )
except (ImportError, ModuleNotFoundError):
    from evaluate import CANONICAL_CIFAR10_TEST_PREFIX_SHA256
    from provenance_schema import (
        content_digest,
        evaluator_identity,
        evidence_payload_digest,
        semantic_digest,
    )


_REQUIRED_ARTIFACTS = {
    "attempt_spec.json",
    "evaluation_manifest.json",
    "evaluation_arrays.npz",
    "run.log",
}
_SPEC_FIELDS = {
    "schema_version",
    "attempt_key",
    "task_id",
    "policy",
    "proposal",
    "effective_config",
    "descriptors",
    "provenance",
    "required_artifacts",
}
_POLICY_FIELDS = {"id", "version"}
_PROPOSAL_FIELDS = {"digest", "record", "change"}
_PROPOSAL_RECORD_FIELDS = {
    "schema_version",
    "domain",
    "schema_id",
    "decision_point",
    "knob",
    "target",
    "cited_knowledge_ids",
    "expected_primary_metric_direction",
    "guardrail_risks",
    "rationale",
}
_CHANGE_FIELDS = {"name", "from", "to"}
_DESCRIPTOR_FIELDS = {"dataset", "environment"}
_DATASET_DESCRIPTOR_FIELDS = {
    "dataset_id",
    "archive_sha256",
    "source",
    "train_split",
    "test_split",
    "train_selector",
    "test_selector",
    "transform",
}
_TRAIN_SELECTOR_FIELDS = {"name", "version", "seed", "count"}
_TEST_SELECTOR_FIELDS = {"name", "version", "count"}
_TRANSFORM_FIELDS = {"name", "version"}
_ENVIRONMENT_DESCRIPTOR_FIELDS = {
    "python",
    "numpy",
    "torch",
    "torchvision",
    "platform_system",
    "platform_machine",
    "requested_device",
    "resolved_device",
}
_EFFECTIVE_CONFIG_FIELDS = {
    "dataset_id",
    "data_source",
    "train_split",
    "test_split",
    "epochs",
    "train_samples",
    "test_samples",
    "batch_size",
    "codebook_size",
    "latent_dim",
    "quantizer_variant",
    "base_learning_rate",
    "device_policy",
    "projection_lr_multiplier",
    "commitment_weight",
    "seed",
    "resolved_device",
}
_SPEC_PROVENANCE_FIELDS = {
    "intervention_digest",
    "config_digest",
    "source_digest",
    "dataset_digest",
    "environment_digest",
    "contract_digest",
    "evaluator_digest",
    "manipulation_status",
}
_MANIFEST_FIELDS = {
    "schema_version",
    "dataset_id",
    "dataset_source",
    "split",
    "epochs_completed",
    "seed",
    "codebook_size",
    "sample_count",
    "train_sample_count",
    "training_protocol",
    "device",
    "model",
    "quantizer_variant",
    "latent_dim",
    "commitment_weight",
    "learning_rate",
    "batch_size",
    "code_revision",
    "git_worktree_dirty",
    "source_sha256",
    "evidence_digest",
    "original_images_prefix_sha256",
    "attempt_spec_sha256",
    "task_id",
    "contract",
    "provenance",
    "intervention",
    "effective_config",
    "descriptors",
    "optimizer",
    "execution",
    "evidence_payload_digest",
}
_MANIFEST_CONTRACT_FIELDS = {"id", "version", "digest"}
_MANIFEST_PROVENANCE_FIELDS = {
    "proposal_digest",
    "intervention_digest",
    "config_digest",
    "source_digest",
    "dataset_digest",
    "environment_digest",
    "evaluator_digest",
    "manipulation_status",
}
_MANIFEST_INTERVENTION_FIELDS = {
    "decision_point",
    "knob",
    "from",
    "to",
    "effective_knobs",
}
_OPTIMIZER_FIELDS = {
    "base_group",
    "base_learning_rate",
    "projection_group",
    "projection_learning_rate",
}
_EXECUTION_FIELDS = {"started_at", "completed_at", "exit_code"}
_ARRAY_NAMES = {
    "original_images",
    "reconstructed_images",
    "codebook_indices",
}
_CIFAR10_ARCHIVE_SHA256 = (
    "6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce"
)


def _invalid(*codes: str) -> dict[str, Any]:
    violations = list(dict.fromkeys(f"evidence_invalid:{code}" for code in codes))
    return {
        "metrics": {},
        "repetitions": 1,
        "failed_repetitions": 1,
        "violations": violations,
    }


def _reject_json_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON number: {token}")


def _reject_duplicate_fields(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    value: dict[str, object] = {}
    for name, item in pairs:
        if name in value:
            raise ValueError(f"duplicate JSON field: {name}")
        value[name] = item
    return value


def _load_json_mapping(
    path: Path, label: str
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(
            path.read_bytes(),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_fields,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None, [f"{label}_missing_or_invalid"]
    if not isinstance(value, dict):
        return None, [f"{label}_not_mapping"]
    return value, []


def _exact_mapping(
    value: object,
    *,
    expected: set[str],
    label: str,
    violations: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        violations.append(f"{label}_not_mapping")
        return None
    actual = set(value)
    violations.extend(
        f"{label}_unknown_field:{field}" for field in sorted(actual - expected)
    )
    violations.extend(
        f"{label}_missing_field:{field}" for field in sorted(expected - actual)
    )
    return value


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _load_contract(path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None, ["contract_missing_or_invalid"]
    if not isinstance(value, dict):
        return None, ["contract_not_mapping"]
    if value.get("schema_version") != 2:
        return None, ["contract_schema_not_two"]
    return value, []


def _load_arrays(path: Path) -> tuple[dict[str, np.ndarray] | None, list[str]]:
    try:
        with np.load(path, allow_pickle=False) as archive:
            actual = set(archive.files)
            if actual != _ARRAY_NAMES:
                codes = [
                    f"missing_array:{name}" for name in sorted(_ARRAY_NAMES - actual)
                ]
                codes.extend(
                    f"unknown_array:{name}" for name in sorted(actual - _ARRAY_NAMES)
                )
                return None, codes
            return {name: archive[name] for name in sorted(_ARRAY_NAMES)}, []
    except (OSError, ValueError):
        return None, ["arrays_missing_or_invalid"]


def _validate_fixed_and_mutable_config(
    *,
    config: dict[str, Any],
    contract: dict[str, Any],
    violations: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = contract["adaptive_experiment"]
    fixed = policy["fixed_config"]
    observed_fixed = {
        key: config.get(key)
        for key in (
            "dataset_id",
            "data_source",
            "train_split",
            "test_split",
            "epochs",
            "train_samples",
            "test_samples",
            "batch_size",
            "codebook_size",
            "latent_dim",
            "quantizer_variant",
            "base_learning_rate",
            "device_policy",
        )
    }
    if observed_fixed != fixed:
        violations.append("fixed_config_mismatch")

    effective_knobs = {name: config.get(name) for name in sorted(policy["knobs"])}
    for name, value in effective_knobs.items():
        allowed = policy["knobs"][name]["allowed_values"]
        if isinstance(value, bool) or type(value) is not float or value not in allowed:
            violations.append(f"knob_not_allowlisted:{name}")
    seed = config.get("seed")
    if type(seed) is not int or seed < 0 or seed >= 2**63:
        violations.append("seed_not_integer")
    if config.get("resolved_device") not in {"cpu", "cuda", "mps"}:
        violations.append("resolved_device_invalid")
    return effective_knobs, policy


def _validate_descriptors(
    *,
    descriptors: dict[str, Any],
    config: dict[str, Any],
    provenance: dict[str, Any],
    violations: list[str],
) -> None:
    dataset = _exact_mapping(
        descriptors.get("dataset"),
        expected=_DATASET_DESCRIPTOR_FIELDS,
        label="dataset_descriptor",
        violations=violations,
    )
    environment = _exact_mapping(
        descriptors.get("environment"),
        expected=_ENVIRONMENT_DESCRIPTOR_FIELDS,
        label="environment_descriptor",
        violations=violations,
    )
    if dataset is None or environment is None:
        return
    train_selector = _exact_mapping(
        dataset.get("train_selector"),
        expected=_TRAIN_SELECTOR_FIELDS,
        label="dataset_train_selector",
        violations=violations,
    )
    test_selector = _exact_mapping(
        dataset.get("test_selector"),
        expected=_TEST_SELECTOR_FIELDS,
        label="dataset_test_selector",
        violations=violations,
    )
    transform = _exact_mapping(
        dataset.get("transform"),
        expected=_TRANSFORM_FIELDS,
        label="dataset_transform",
        violations=violations,
    )
    if train_selector is None or test_selector is None or transform is None:
        return
    expected_dataset = {
        "dataset_id": config["dataset_id"],
        "archive_sha256": _CIFAR10_ARCHIVE_SHA256,
        "source": config["data_source"],
        "train_split": config["train_split"],
        "test_split": config["test_split"],
        "train_selector": {
            "name": "torch_randperm_without_replacement",
            "version": "1",
            "seed": config["seed"],
            "count": config["train_samples"],
        },
        "test_selector": {
            "name": "canonical_prefix",
            "version": "1",
            "count": config["test_samples"],
        },
        "transform": {
            "name": "torchvision.transforms.ToTensor",
            "version": "1",
        },
    }
    if dataset != expected_dataset:
        violations.append("dataset_descriptor_mismatch")
    for field in (
        "python",
        "numpy",
        "torch",
        "torchvision",
        "platform_system",
        "platform_machine",
    ):
        value = environment.get(field)
        if not isinstance(value, str) or not value or "/" in value or "\\" in value:
            violations.append(f"environment_descriptor_invalid:{field}")
    if (
        environment.get("requested_device") != config["device_policy"]
        or environment.get("resolved_device") != config["resolved_device"]
    ):
        violations.append("environment_descriptor_config_mismatch")
    if provenance.get("dataset_digest") != semantic_digest(
        "ai-researcher/dataset-plan/v1",
        dataset,
    ):
        violations.append("dataset_digest_mismatch")
    if provenance.get("environment_digest") != semantic_digest(
        "ai-researcher/environment/v1",
        environment,
    ):
        violations.append("environment_digest_mismatch")


def _validate_proposal(
    *,
    proposal: dict[str, Any],
    policy: dict[str, Any],
    effective_knobs: dict[str, Any],
    manipulation_status: object,
    violations: list[str],
) -> None:
    record = _exact_mapping(
        proposal.get("record"),
        expected=_PROPOSAL_RECORD_FIELDS,
        label="proposal_record",
        violations=violations,
    )
    change = proposal.get("change")
    if change is not None:
        change = _exact_mapping(
            change,
            expected=_CHANGE_FIELDS,
            label="proposal_change",
            violations=violations,
        )
    if record is None or (proposal.get("change") is not None and change is None):
        return
    if (
        record.get("schema_version") != "1"
        or record.get("domain") != "vq"
        or record.get("schema_id") != "vq.intervention/v1"
        or record.get("decision_point") != policy["decision_point"]
    ):
        violations.append("proposal_record_identity_mismatch")
    if not isinstance(record.get("rationale"), str) or not record["rationale"]:
        violations.append("proposal_rationale_invalid")
    for field in ("cited_knowledge_ids", "guardrail_risks"):
        values = record.get(field)
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            violations.append(f"proposal_{field}_invalid")
    if record.get("expected_primary_metric_direction") not in {
        "increase",
        "decrease",
        "unchanged",
    }:
        violations.append("proposal_direction_invalid")
    expected_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        record,
    )
    if proposal.get("digest") != expected_digest:
        violations.append("proposal_digest_mismatch")

    if change is None:
        if (
            record.get("knob") is not None
            or record.get("target") is not None
            or manipulation_status != "baseline"
            or effective_knobs != policy["defaults"]
        ):
            violations.append("baseline_proposal_mismatch")
        return

    knob = change.get("name")
    if knob not in policy["knobs"]:
        violations.append("proposal_knob_not_allowlisted")
        return
    allowed = policy["knobs"][knob]["allowed_values"]
    from_value = change.get("from")
    to_value = change.get("to")
    if (
        type(from_value) is not float
        or from_value not in allowed
        or type(to_value) is not float
        or to_value not in allowed
    ):
        violations.append("proposal_change_value_not_allowlisted")
    if (
        record.get("knob") != knob
        or record.get("target") != to_value
        or effective_knobs.get(knob) != to_value
    ):
        violations.append("proposal_change_config_mismatch")
    expected_status = "no_effect" if from_value == to_value else "changed"
    if manipulation_status != expected_status:
        violations.append("manipulation_status_mismatch")


def _validate_execution(value: dict[str, Any], violations: list[str]) -> None:
    if value.get("exit_code") != 0:
        violations.append("execution_exit_code_not_zero")
    try:
        started = datetime.fromisoformat(value["started_at"])
        completed = datetime.fromisoformat(value["completed_at"])
    except (KeyError, TypeError, ValueError):
        violations.append("execution_timestamp_invalid")
        return
    if started.tzinfo is None or completed.tzinfo is None or completed < started:
        violations.append("execution_timestamp_invalid")


def evaluate_attempt_v3(
    attempt_dir: str | Path,
    *,
    contract_path: str | Path,
    expected_originals_sha256: str | None = (CANONICAL_CIFAR10_TEST_PREFIX_SHA256),
) -> dict[str, Any]:
    """Verify V3 provenance and compute metrics only from raw evidence."""

    root = Path(attempt_dir)
    contract_file = Path(contract_path)
    if not contract_file.is_absolute() and not contract_file.is_file():
        contract_file = Path(__file__).resolve().parent / contract_file
    contract_file = contract_file.resolve()
    contract, violations = _load_contract(contract_file)
    if contract is None:
        return _invalid(*violations)

    required = contract.get("required_artifacts")
    if (
        not isinstance(required, list)
        or set(required) != _REQUIRED_ARTIFACTS
        or len(required) != len(set(required))
        or any(Path(name).name != name for name in required)
    ):
        violations.append("contract_required_artifacts_invalid")
    violations.extend(
        f"missing_artifact:{name}"
        for name in sorted(_REQUIRED_ARTIFACTS)
        if not (root / name).is_file()
    )
    if violations:
        return _invalid(*violations)

    spec_path = root / "attempt_spec.json"
    manifest_path = root / "evaluation_manifest.json"
    spec, spec_errors = _load_json_mapping(spec_path, "attempt_spec")
    manifest, manifest_errors = _load_json_mapping(
        manifest_path,
        "manifest",
    )
    arrays, array_errors = _load_arrays(root / "evaluation_arrays.npz")
    violations.extend(spec_errors)
    violations.extend(manifest_errors)
    violations.extend(array_errors)
    if spec is None or manifest is None or arrays is None:
        return _invalid(*violations)

    _exact_mapping(
        spec,
        expected=_SPEC_FIELDS,
        label="attempt_spec",
        violations=violations,
    )
    policy_ref = _exact_mapping(
        spec.get("policy"),
        expected=_POLICY_FIELDS,
        label="attempt_spec_policy",
        violations=violations,
    )
    proposal = _exact_mapping(
        spec.get("proposal"),
        expected=_PROPOSAL_FIELDS,
        label="attempt_spec_proposal",
        violations=violations,
    )
    config = _exact_mapping(
        spec.get("effective_config"),
        expected=_EFFECTIVE_CONFIG_FIELDS,
        label="attempt_spec_effective_config",
        violations=violations,
    )
    descriptors = _exact_mapping(
        spec.get("descriptors"),
        expected=_DESCRIPTOR_FIELDS,
        label="attempt_spec_descriptors",
        violations=violations,
    )
    provenance = _exact_mapping(
        spec.get("provenance"),
        expected=_SPEC_PROVENANCE_FIELDS,
        label="attempt_spec_provenance",
        violations=violations,
    )
    _exact_mapping(
        manifest,
        expected=_MANIFEST_FIELDS,
        label="manifest",
        violations=violations,
    )
    manifest_contract = _exact_mapping(
        manifest.get("contract"),
        expected=_MANIFEST_CONTRACT_FIELDS,
        label="manifest_contract",
        violations=violations,
    )
    manifest_provenance = _exact_mapping(
        manifest.get("provenance"),
        expected=_MANIFEST_PROVENANCE_FIELDS,
        label="manifest_provenance",
        violations=violations,
    )
    manifest_intervention = _exact_mapping(
        manifest.get("intervention"),
        expected=_MANIFEST_INTERVENTION_FIELDS,
        label="manifest_intervention",
        violations=violations,
    )
    optimizer = _exact_mapping(
        manifest.get("optimizer"),
        expected=_OPTIMIZER_FIELDS,
        label="manifest_optimizer",
        violations=violations,
    )
    execution = _exact_mapping(
        manifest.get("execution"),
        expected=_EXECUTION_FIELDS,
        label="manifest_execution",
        violations=violations,
    )
    if (
        violations
        or policy_ref is None
        or proposal is None
        or config is None
        or descriptors is None
        or provenance is None
        or manifest_contract is None
        or manifest_provenance is None
        or manifest_intervention is None
        or optimizer is None
        or execution is None
    ):
        return _invalid(*violations)

    policy = contract.get("adaptive_experiment")
    if not isinstance(policy, dict):
        return _invalid("contract_adaptive_policy_missing")
    if (
        spec.get("schema_version") != 1
        or spec.get("task_id") != contract.get("task_id")
        or policy_ref
        != {"id": policy.get("policy_id"), "version": policy.get("version")}
        or spec.get("required_artifacts") != required
    ):
        violations.append("attempt_spec_contract_mismatch")

    contract_digest = content_digest(
        "ai-researcher/contract/v1",
        contract_file.read_bytes(),
    )
    try:
        evaluator_digest = evaluator_identity(contract, contract_file.parent)
    except (OSError, ValueError):
        return _invalid("evaluator_identity_invalid")
    source_digest = policy.get("expected_source_digest")
    if not _is_sha256(source_digest):
        violations.append("contract_source_digest_invalid")
    expected_spec_sha256 = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    if manifest.get("attempt_spec_sha256") != expected_spec_sha256:
        violations.append("attempt_spec_sha256_mismatch")
    if provenance.get("contract_digest") != contract_digest:
        violations.append("contract_digest_mismatch")
    if provenance.get("evaluator_digest") != evaluator_digest:
        violations.append("evaluator_digest_mismatch")
    if provenance.get("source_digest") != source_digest:
        violations.append("source_digest_mismatch")
    for field in _SPEC_PROVENANCE_FIELDS - {"manipulation_status"}:
        if not _is_sha256(provenance.get(field)):
            violations.append(f"provenance_digest_invalid:{field}")

    effective_knobs, policy = _validate_fixed_and_mutable_config(
        config=config,
        contract=contract,
        violations=violations,
    )
    _validate_descriptors(
        descriptors=descriptors,
        config=config,
        provenance=provenance,
        violations=violations,
    )
    expected_intervention_digest = semantic_digest(
        "ai-researcher/intervention/v1",
        effective_knobs,
    )
    if provenance.get("intervention_digest") != expected_intervention_digest:
        violations.append("intervention_digest_mismatch")
    expected_config_digest = semantic_digest(
        "ai-researcher/run-config/v1",
        config,
    )
    if provenance.get("config_digest") != expected_config_digest:
        violations.append("config_digest_mismatch")
    _validate_proposal(
        proposal=proposal,
        policy=policy,
        effective_knobs=effective_knobs,
        manipulation_status=provenance.get("manipulation_status"),
        violations=violations,
    )

    expected_contract_receipt = {
        "id": contract["contract_id"],
        "version": contract["version"],
        "digest": contract_digest,
    }
    if manifest_contract != expected_contract_receipt:
        violations.append("manifest_contract_mismatch")
    expected_manifest_provenance = {
        "proposal_digest": proposal.get("digest"),
        "intervention_digest": provenance.get("intervention_digest"),
        "config_digest": provenance.get("config_digest"),
        "source_digest": provenance.get("source_digest"),
        "dataset_digest": provenance.get("dataset_digest"),
        "environment_digest": provenance.get("environment_digest"),
        "evaluator_digest": provenance.get("evaluator_digest"),
        "manipulation_status": provenance.get("manipulation_status"),
    }
    if manifest_provenance != expected_manifest_provenance:
        violations.append("manifest_provenance_mismatch")
    if manifest.get("effective_config") != config:
        violations.append("manifest_effective_config_mismatch")
    if manifest.get("descriptors") != descriptors:
        violations.append("manifest_descriptors_mismatch")

    record = proposal["record"]
    change = proposal["change"]
    expected_manifest_intervention = {
        "decision_point": record["decision_point"],
        "knob": change["name"] if change is not None else None,
        "from": change["from"] if change is not None else None,
        "to": change["to"] if change is not None else None,
        "effective_knobs": effective_knobs,
    }
    if manifest_intervention != expected_manifest_intervention:
        violations.append("manifest_intervention_mismatch")
    expected_optimizer = {
        "base_group": "base",
        "base_learning_rate": config["base_learning_rate"],
        "projection_group": "code_projection",
        "projection_learning_rate": (
            config["base_learning_rate"] * config["projection_lr_multiplier"]
        ),
    }
    if optimizer != expected_optimizer:
        violations.append("manifest_optimizer_mismatch")
    _validate_execution(execution, violations)

    legacy_expectations = {
        "schema_version": 2,
        "dataset_id": config["dataset_id"],
        "dataset_source": config["data_source"],
        "split": config["test_split"],
        "epochs_completed": config["epochs"],
        "seed": config["seed"],
        "codebook_size": config["codebook_size"],
        "sample_count": config["test_samples"],
        "train_sample_count": config["train_samples"],
        "training_protocol": "deterministic_subset_without_replacement",
        "device": config["resolved_device"],
        "model": f"{config['quantizer_variant']}_smoke_autoencoder",
        "quantizer_variant": config["quantizer_variant"],
        "latent_dim": config["latent_dim"],
        "commitment_weight": config["commitment_weight"],
        "learning_rate": config["base_learning_rate"],
        "batch_size": config["batch_size"],
        "task_id": contract["task_id"],
    }
    for field, expected in legacy_expectations.items():
        if manifest.get(field) != expected:
            violations.append(f"manifest_field_mismatch:{field}")
    if (
        not isinstance(manifest.get("code_revision"), str)
        or not manifest["code_revision"]
        or type(manifest.get("git_worktree_dirty")) is not bool
        or not _is_sha256(manifest.get("source_sha256"))
    ):
        violations.append("manifest_source_receipt_invalid")

    originals = arrays["original_images"]
    reconstructions = arrays["reconstructed_images"]
    indices = arrays["codebook_indices"]
    sample_count = config["test_samples"]
    codebook_size = config["codebook_size"]
    if originals.dtype != np.uint8 or reconstructions.dtype != np.uint8:
        violations.append("image_dtype_not_uint8")
    if (
        originals.ndim != 4
        or reconstructions.ndim != 4
        or originals.shape != reconstructions.shape
        or originals.shape[0] != sample_count
    ):
        violations.append("image_shape_mismatch")
    elif originals.shape[-1] not in {1, 3} and originals.shape[1] not in {1, 3}:
        violations.append("image_channel_dimension_invalid")
    if (
        not np.issubdtype(indices.dtype, np.integer)
        or indices.ndim < 1
        or indices.size == 0
        or indices.shape[0] != sample_count
    ):
        violations.append("indices_invalid")
    elif int(indices.min()) < 0 or int(indices.max()) >= codebook_size:
        violations.append("index_out_of_range")
    if violations:
        return _invalid(*violations)

    originals_prefix_digest = hashlib.sha256(originals[:1024].tobytes()).hexdigest()
    if (
        expected_originals_sha256 is not None
        and originals_prefix_digest != expected_originals_sha256
    ):
        violations.append("cifar10_test_prefix_digest_mismatch")
    if manifest.get("original_images_prefix_sha256") != originals_prefix_digest:
        violations.append("original_images_prefix_digest_mismatch")
    payload_digest = evidence_payload_digest(arrays)
    if manifest.get("evidence_payload_digest") != payload_digest:
        violations.append("evidence_payload_digest_mismatch")
    legacy_digest = hashlib.sha256(
        originals.tobytes() + reconstructions.tobytes() + indices.tobytes()
    ).hexdigest()
    if manifest.get("evidence_digest") != legacy_digest:
        violations.append("legacy_evidence_digest_mismatch")
    if violations:
        return _invalid(*violations)

    originals_float = originals.astype(np.float64) / 255.0
    reconstructions_float = reconstructions.astype(np.float64) / 255.0
    reconstruction_mse = float(
        np.mean(np.square(originals_float - reconstructions_float))
    )
    psnr_denominator = max(
        reconstruction_mse,
        np.finfo(np.float64).eps,
    )
    reconstruction_psnr_db = 10.0 * math.log10(1.0 / psnr_denominator)
    counts = np.bincount(indices.reshape(-1), minlength=codebook_size)
    active_counts = counts[counts > 0]
    probabilities = active_counts.astype(np.float64) / float(indices.size)
    codebook_perplexity = float(np.exp(-np.sum(probabilities * np.log(probabilities))))
    metrics = {
        "codebook_utilization": int(active_counts.size) / codebook_size,
        "active_codes": int(active_counts.size),
        "codebook_perplexity": codebook_perplexity,
        "reconstruction_mse": reconstruction_mse,
        "reconstruction_psnr_db": reconstruction_psnr_db,
    }
    for name, bounds in (
        contract.get("validity", {})
        .get(
            "metric_bounds",
            {},
        )
        .items()
    ):
        value = metrics.get(name)
        if value is None:
            violations.append(f"missing_bounded_metric:{name}")
            continue
        if bounds.get("minimum") is not None and value < bounds["minimum"]:
            violations.append(f"metric_below_minimum:{name}")
        if bounds.get("maximum") is not None and value > bounds["maximum"]:
            violations.append(f"metric_above_maximum:{name}")
    if violations:
        return _invalid(*violations)
    return {
        "metrics": metrics,
        "repetitions": 1,
        "failed_repetitions": 0,
        "violations": [],
    }


def main(attempt_dir: str, *, contract_path: str | Path) -> int:
    root = Path(attempt_dir)
    result = evaluate_attempt_v3(
        root,
        contract_path=contract_path,
    )
    (root / "verification_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_dir")
    parser.add_argument(
        "--contract",
        default="contract.closed_loop_v3.yaml",
    )
    arguments = parser.parse_args()
    raise SystemExit(
        main(
            arguments.attempt_dir,
            contract_path=arguments.contract,
        )
    )
