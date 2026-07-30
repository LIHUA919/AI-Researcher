"""Strict loader for a frozen VQ adaptive-experiment Attempt Spec."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping


SPEC_PATH_ENV = "AI_RESEARCHER_ATTEMPT_SPEC"
SPEC_SHA256_ENV = "AI_RESEARCHER_ATTEMPT_SPEC_SHA256"
_TOP_LEVEL_FIELDS = {
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
_PROVENANCE_FIELDS = {
    "intervention_digest",
    "config_digest",
    "source_digest",
    "dataset_digest",
    "environment_digest",
    "contract_digest",
    "evaluator_digest",
    "manipulation_status",
}
_FIXED_CONFIG: dict[str, object] = {
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
}
_ALLOWED_PROJECTION_LR_MULTIPLIERS = (0.25, 0.5, 1.0, 2.0, 4.0)
_ALLOWED_COMMITMENT_WEIGHTS = (0.1, 0.25, 0.5, 1.0)
_CIFAR10_ARCHIVE_SHA256 = (
    "6d958be074577803d12ecdefd02955f39262c83c16fe9348329d7fe0b5c001ce"
)
_REQUIRED_ARTIFACTS = [
    "attempt_spec.json",
    "evaluation_manifest.json",
    "evaluation_arrays.npz",
    "run.log",
]


class AttemptSpecError(ValueError):
    """Raised when an Attempt Spec cannot be trusted for execution."""


@dataclass(frozen=True)
class LoadedAttemptSpec:
    path: Path
    sha256: str
    payload: dict[str, object]

    @property
    def output_dir(self) -> Path:
        return self.path.parent


def semantic_digest(domain: str, value: object) -> str:
    """Hash a JSON semantic value with a domain separator."""

    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AttemptSpecError("digest value must be finite JSON") from exc
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _require_exact_fields(
    value: object,
    *,
    name: str,
    expected: set[str],
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AttemptSpecError(f"{name} must be a JSON object")
    actual = set(value)
    unknown = sorted(actual - expected)
    if unknown:
        raise AttemptSpecError(f"{name} has unknown field: {unknown[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise AttemptSpecError(f"{name} is missing field: {missing[0]}")
    return value


def _validate_structure(payload: dict[str, object]) -> None:
    _require_exact_fields(
        payload,
        name="Attempt Spec",
        expected=_TOP_LEVEL_FIELDS,
    )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise AttemptSpecError("unsupported Attempt Spec schema_version")
    if not isinstance(payload["attempt_key"], str) or not payload["attempt_key"]:
        raise AttemptSpecError("attempt_key must be a non-empty string")
    if payload["task_id"] != "one_layer_vq:task1":
        raise AttemptSpecError("Attempt Spec task_id mismatch")
    policy = _require_exact_fields(
        payload["policy"],
        name="policy",
        expected=_POLICY_FIELDS,
    )
    if policy != {"id": "one-layer-vq-phase-a", "version": "1"}:
        raise AttemptSpecError("Attempt Spec policy mismatch")
    if payload["required_artifacts"] != _REQUIRED_ARTIFACTS:
        raise AttemptSpecError("Attempt Spec required_artifacts mismatch")
    proposal = _require_exact_fields(
        payload["proposal"],
        name="proposal",
        expected=_PROPOSAL_FIELDS,
    )
    proposal_record = _require_exact_fields(
        proposal["record"],
        name="proposal.record",
        expected=_PROPOSAL_RECORD_FIELDS,
    )
    change = proposal["change"]
    if change is not None:
        change = _require_exact_fields(
            change,
            name="proposal.change",
            expected=_CHANGE_FIELDS,
        )
    if (
        proposal_record["schema_version"] != "1"
        or proposal_record["domain"] != "vq"
        or proposal_record["schema_id"] != "vq.intervention/v1"
        or proposal_record["decision_point"] != "vq.quantizer_optimization"
    ):
        raise AttemptSpecError("proposal record identity mismatch")
    for field in ("cited_knowledge_ids", "guardrail_risks"):
        values = proposal_record[field]
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise AttemptSpecError(f"proposal {field} must be unique strings")
    if proposal_record["expected_primary_metric_direction"] not in {
        "increase",
        "decrease",
        "unchanged",
    }:
        raise AttemptSpecError("proposal direction is invalid")
    if (
        not isinstance(proposal_record["rationale"], str)
        or not proposal_record["rationale"]
    ):
        raise AttemptSpecError("proposal rationale must be non-empty")
    effective_config = _require_exact_fields(
        payload["effective_config"],
        name="effective_config",
        expected=_EFFECTIVE_CONFIG_FIELDS,
    )
    for field, expected in _FIXED_CONFIG.items():
        if type(effective_config[field]) is not type(expected) or (
            effective_config[field] != expected
        ):
            raise AttemptSpecError(f"fixed config mismatch: {field}")
    projection_multiplier = effective_config["projection_lr_multiplier"]
    if (
        type(projection_multiplier) is not float
        or projection_multiplier not in _ALLOWED_PROJECTION_LR_MULTIPLIERS
    ):
        raise AttemptSpecError("invalid effective config: projection_lr_multiplier")
    commitment_weight = effective_config["commitment_weight"]
    if (
        type(commitment_weight) is not float
        or commitment_weight not in _ALLOWED_COMMITMENT_WEIGHTS
    ):
        raise AttemptSpecError("invalid effective config: commitment_weight")
    seed = effective_config["seed"]
    if type(seed) is not int or seed < 0 or seed >= 2**63:
        raise AttemptSpecError("invalid effective config: seed")
    if effective_config["resolved_device"] not in {"cpu", "cuda", "mps"}:
        raise AttemptSpecError("invalid effective config: resolved_device")
    descriptors = _require_exact_fields(
        payload["descriptors"],
        name="descriptors",
        expected=_DESCRIPTOR_FIELDS,
    )
    dataset_descriptor = _require_exact_fields(
        descriptors["dataset"],
        name="descriptors.dataset",
        expected=_DATASET_DESCRIPTOR_FIELDS,
    )
    train_selector = _require_exact_fields(
        dataset_descriptor["train_selector"],
        name="descriptors.dataset.train_selector",
        expected=_TRAIN_SELECTOR_FIELDS,
    )
    test_selector = _require_exact_fields(
        dataset_descriptor["test_selector"],
        name="descriptors.dataset.test_selector",
        expected=_TEST_SELECTOR_FIELDS,
    )
    transform = _require_exact_fields(
        dataset_descriptor["transform"],
        name="descriptors.dataset.transform",
        expected=_TRANSFORM_FIELDS,
    )
    expected_dataset_descriptor = {
        "dataset_id": effective_config["dataset_id"],
        "archive_sha256": _CIFAR10_ARCHIVE_SHA256,
        "source": effective_config["data_source"],
        "train_split": effective_config["train_split"],
        "test_split": effective_config["test_split"],
        "train_selector": {
            "name": "torch_randperm_without_replacement",
            "version": "1",
            "seed": effective_config["seed"],
            "count": effective_config["train_samples"],
        },
        "test_selector": {
            "name": "canonical_prefix",
            "version": "1",
            "count": effective_config["test_samples"],
        },
        "transform": {
            "name": "torchvision.transforms.ToTensor",
            "version": "1",
        },
    }
    if (
        dataset_descriptor != expected_dataset_descriptor
        or train_selector != expected_dataset_descriptor["train_selector"]
        or test_selector != expected_dataset_descriptor["test_selector"]
        or transform != expected_dataset_descriptor["transform"]
    ):
        raise AttemptSpecError("dataset descriptor does not match effective config")
    environment_descriptor = _require_exact_fields(
        descriptors["environment"],
        name="descriptors.environment",
        expected=_ENVIRONMENT_DESCRIPTOR_FIELDS,
    )
    for field in (
        "python",
        "numpy",
        "torch",
        "torchvision",
        "platform_system",
        "platform_machine",
    ):
        value = environment_descriptor[field]
        if not isinstance(value, str) or not value or "/" in value or "\\" in value:
            raise AttemptSpecError(f"environment descriptor field is invalid: {field}")
    if (
        environment_descriptor["requested_device"] != effective_config["device_policy"]
        or environment_descriptor["resolved_device"]
        != effective_config["resolved_device"]
    ):
        raise AttemptSpecError("environment descriptor does not match effective config")
    provenance = _require_exact_fields(
        payload["provenance"],
        name="provenance",
        expected=_PROVENANCE_FIELDS,
    )
    mutable_config = {
        "commitment_weight": effective_config["commitment_weight"],
        "projection_lr_multiplier": effective_config["projection_lr_multiplier"],
    }
    if provenance["intervention_digest"] != semantic_digest(
        "ai-researcher/intervention/v1",
        mutable_config,
    ):
        raise AttemptSpecError("intervention_digest mismatch")
    if provenance["config_digest"] != semantic_digest(
        "ai-researcher/run-config/v1",
        effective_config,
    ):
        raise AttemptSpecError("config_digest mismatch")
    if provenance["dataset_digest"] != semantic_digest(
        "ai-researcher/dataset-plan/v1",
        dataset_descriptor,
    ):
        raise AttemptSpecError("dataset_digest mismatch")
    if provenance["environment_digest"] != semantic_digest(
        "ai-researcher/environment/v1",
        environment_descriptor,
    ):
        raise AttemptSpecError("environment_digest mismatch")
    for field in (
        "intervention_digest",
        "config_digest",
        "source_digest",
        "dataset_digest",
        "environment_digest",
        "contract_digest",
        "evaluator_digest",
    ):
        if not _is_sha256(provenance[field]):
            raise AttemptSpecError(f"provenance {field} must be lowercase SHA-256")
    if proposal["digest"] != semantic_digest(
        "ai-researcher/proposal/v1",
        proposal_record,
    ):
        raise AttemptSpecError("proposal digest mismatch")
    manipulation_status = provenance["manipulation_status"]
    if change is None:
        if (
            proposal_record["knob"] is not None
            or proposal_record["target"] is not None
            or manipulation_status != "baseline"
            or mutable_config
            != {
                "commitment_weight": 0.25,
                "projection_lr_multiplier": 1.0,
            }
        ):
            raise AttemptSpecError("baseline proposal cannot select a knob")
    else:
        knob = change["name"]
        allowed_by_knob = {
            "projection_lr_multiplier": _ALLOWED_PROJECTION_LR_MULTIPLIERS,
            "commitment_weight": _ALLOWED_COMMITMENT_WEIGHTS,
        }
        if knob not in allowed_by_knob:
            raise AttemptSpecError("proposal change selects an unknown knob")
        from_value = change["from"]
        to_value = change["to"]
        if (
            type(from_value) is not float
            or from_value not in allowed_by_knob[knob]
            or type(to_value) is not float
            or to_value not in allowed_by_knob[knob]
        ):
            raise AttemptSpecError("proposal change is outside the allowlist")
        if (
            proposal_record["knob"] != knob
            or proposal_record["target"] != to_value
            or mutable_config[knob] != to_value
        ):
            raise AttemptSpecError("proposal change does not match effective config")
        expected_status = "no_effect" if from_value == to_value else "changed"
        if manipulation_status != expected_status:
            raise AttemptSpecError("manipulation_status does not match proposal change")


def load_attempt_spec_from_environment(
    environ: Mapping[str, str] | None = None,
) -> LoadedAttemptSpec:
    """Load an Attempt Spec only after verifying its exact file bytes."""

    source = os.environ if environ is None else environ
    try:
        raw_path = source[SPEC_PATH_ENV]
        expected_sha256 = source[SPEC_SHA256_ENV]
    except KeyError as exc:
        raise AttemptSpecError(
            f"missing required environment variable: {exc.args[0]}"
        ) from exc

    path = Path(raw_path)
    if not path.is_absolute():
        raise AttemptSpecError(f"{SPEC_PATH_ENV} must be an absolute path")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise AttemptSpecError(f"cannot read Attempt Spec: {path}") from exc
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise AttemptSpecError("Attempt Spec SHA-256 mismatch")

    def reject_non_finite(token: str) -> object:
        raise AttemptSpecError(
            f"Attempt Spec values must be finite JSON numbers, got {token}"
        )

    def reject_duplicate_fields(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        value: dict[str, object] = {}
        for name, item in pairs:
            if name in value:
                raise AttemptSpecError(f"duplicate JSON field: {name}")
            value[name] = item
        return value

    try:
        payload = json.loads(
            content,
            parse_constant=reject_non_finite,
            object_pairs_hook=reject_duplicate_fields,
        )
    except AttemptSpecError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AttemptSpecError("Attempt Spec must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise AttemptSpecError("Attempt Spec must be a JSON object")
    _validate_structure(payload)
    return LoadedAttemptSpec(
        path=path,
        sha256=actual_sha256,
        payload=payload,
    )
