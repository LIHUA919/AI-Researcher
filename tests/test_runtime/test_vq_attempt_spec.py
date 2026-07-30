from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from benchmark.process.dataset_candidate.vq.attempt_spec import (
    AttemptSpecError,
    load_attempt_spec_from_environment,
)
from research_agent.inno.experience import (
    Hypothesis,
    load_evaluation_contract,
)
from research_agent.runtime.adaptive_experiment import AdaptiveExperimentRequest
from research_agent.runtime.domain_adapters.vq import VQExperimentDomainAdapter


def _semantic_digest(domain: str, value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(domain.encode("ascii") + b"\0" + payload).hexdigest()


def _write_valid_spec(root: Path) -> tuple[Path, str, dict[str, object]]:
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
        "rationale": "Test the projection-specific learning rate.",
    }
    proposal = {
        "digest": _semantic_digest(
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
    mutable_config = {
        "commitment_weight": 0.25,
        "projection_lr_multiplier": 2.0,
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
    payload: dict[str, object] = {
        "schema_version": 1,
        "attempt_key": "seed-401:treatment:iteration-002",
        "task_id": "one_layer_vq:task1",
        "policy": {"id": "one-layer-vq-phase-a", "version": "1"},
        "proposal": proposal,
        "effective_config": effective_config,
        "descriptors": descriptors,
        "provenance": {
            "intervention_digest": _semantic_digest(
                "ai-researcher/intervention/v1",
                mutable_config,
            ),
            "config_digest": _semantic_digest(
                "ai-researcher/run-config/v1",
                effective_config,
            ),
            "source_digest": "1" * 64,
            "dataset_digest": _semantic_digest(
                "ai-researcher/dataset-plan/v1",
                descriptors["dataset"],
            ),
            "environment_digest": _semantic_digest(
                "ai-researcher/environment/v1",
                descriptors["environment"],
            ),
            "contract_digest": "4" * 64,
            "evaluator_digest": "5" * 64,
            "manipulation_status": "changed",
        },
        "required_artifacts": [
            "attempt_spec.json",
            "evaluation_manifest.json",
            "evaluation_arrays.npz",
            "run.log",
        ],
    }
    root.mkdir(parents=True, exist_ok=True)
    path = root / "attempt_spec.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return path, sha256, payload


def _environment_for(path: Path) -> dict[str, str]:
    return {
        "AI_RESEARCHER_ATTEMPT_SPEC": str(path),
        "AI_RESEARCHER_ATTEMPT_SPEC_SHA256": hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
    }


def test_valid_attempt_spec_is_loaded_from_verified_absolute_path(tmp_path):
    path, sha256, payload = _write_valid_spec(tmp_path / "raw-evidence")

    loaded = load_attempt_spec_from_environment(
        {
            "AI_RESEARCHER_ATTEMPT_SPEC": str(path),
            "AI_RESEARCHER_ATTEMPT_SPEC_SHA256": sha256,
        }
    )

    assert loaded.payload == payload
    assert loaded.path == path
    assert loaded.sha256 == sha256
    assert loaded.output_dir == path.parent


def test_attempt_spec_rejects_unknown_fields_at_every_level(tmp_path):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    payload["unexpected"] = "not allowed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AttemptSpecError, match="unknown field.*unexpected"):
        load_attempt_spec_from_environment(_environment_for(path))


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_attempt_spec_rejects_non_finite_numbers(tmp_path, non_finite):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    config = payload["effective_config"]
    assert isinstance(config, dict)
    config["commitment_weight"] = non_finite
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AttemptSpecError, match="finite JSON number"):
        load_attempt_spec_from_environment(_environment_for(path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset_id", "synthetic"),
        ("epochs", 3),
        ("codebook_size", 256),
        ("quantizer_variant", "vanilla"),
        ("base_learning_rate", 0.001),
    ],
)
def test_attempt_spec_rejects_changes_to_fixed_protocol_config(
    tmp_path,
    field,
    value,
):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    config = payload["effective_config"]
    assert isinstance(config, dict)
    config[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AttemptSpecError, match=f"fixed config mismatch: {field}"):
        load_attempt_spec_from_environment(_environment_for(path))


def test_v3_entrypoint_maps_verified_spec_to_frozen_protocol_arguments(
    tmp_path,
    monkeypatch,
):
    path, sha256, payload = _write_valid_spec(tmp_path / "raw-evidence")
    captured: list[argparse.Namespace] = []

    def build_parser() -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--data-dir", required=True)
        parser.add_argument("--data-source")
        parser.add_argument("--device")
        parser.add_argument("--seed", type=int)
        parser.add_argument("--epochs", type=int)
        parser.add_argument("--train-samples", type=int)
        parser.add_argument("--test-samples", type=int)
        parser.add_argument("--batch-size", type=int)
        parser.add_argument("--codebook-size", type=int)
        parser.add_argument("--latent-dim", type=int)
        parser.add_argument("--variant")
        parser.add_argument("--commitment-weight", type=float)
        parser.add_argument("--learning-rate", type=float)
        parser.add_argument("--projection-lr-multiplier", type=float)
        parser.add_argument("--overwrite", action="store_true")
        return parser

    monkeypatch.setitem(
        sys.modules,
        "protocol",
        SimpleNamespace(build_parser=build_parser, run=captured.append),
    )
    entrypoint = (
        Path(__file__).resolve().parents[2]
        / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
    )
    spec = importlib.util.spec_from_file_location("vq_v3_entrypoint", entrypoint)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("AI_RESEARCHER_ATTEMPT_SPEC", str(path))
    monkeypatch.setenv("AI_RESEARCHER_ATTEMPT_SPEC_SHA256", sha256)
    monkeypatch.setattr(sys, "argv", [str(entrypoint)])

    assert module.main() == 0

    [arguments] = captured
    config = payload["effective_config"]
    assert isinstance(config, dict)
    assert Path(arguments.output_dir) == path.parent
    assert Path(arguments.data_dir) == entrypoint.parent / "data"
    assert arguments.seed == config["seed"]
    assert arguments.projection_lr_multiplier == 2.0
    assert arguments.commitment_weight == 0.25
    assert arguments.overwrite is False
    assert arguments._attempt_spec_payload == payload
    assert arguments._attempt_spec_sha256 == sha256


def test_attempt_spec_recomputes_intervention_and_config_digests(tmp_path):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    config = payload["effective_config"]
    assert isinstance(config, dict)
    config["projection_lr_multiplier"] = 4.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AttemptSpecError, match="intervention_digest mismatch"):
        load_attempt_spec_from_environment(_environment_for(path))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("projection_lr_multiplier", True),
        ("projection_lr_multiplier", 1.0000000001),
        ("commitment_weight", 0.3),
        ("seed", True),
        ("resolved_device", "auto"),
    ],
)
def test_attempt_spec_rejects_non_strict_or_non_allowlisted_config_values(
    tmp_path,
    field,
    value,
):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    config = payload["effective_config"]
    assert isinstance(config, dict)
    config[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        AttemptSpecError,
        match=f"invalid effective config: {field}",
    ):
        load_attempt_spec_from_environment(_environment_for(path))


def test_attempt_spec_accepts_system_generated_baseline_proposal(tmp_path):
    path, _, payload = _write_valid_spec(tmp_path / "raw-evidence")
    config = payload["effective_config"]
    proposal = payload["proposal"]
    provenance = payload["provenance"]
    assert isinstance(config, dict)
    assert isinstance(proposal, dict)
    assert isinstance(provenance, dict)
    record = proposal["record"]
    assert isinstance(record, dict)
    config["projection_lr_multiplier"] = 1.0
    record["knob"] = None
    record["target"] = None
    record["cited_knowledge_ids"] = []
    record["expected_primary_metric_direction"] = "unchanged"
    record["rationale"] = "System-generated Intervention Catalog baseline."
    proposal["change"] = None
    proposal["digest"] = _semantic_digest(
        "ai-researcher/proposal/v1",
        record,
    )
    provenance["intervention_digest"] = _semantic_digest(
        "ai-researcher/intervention/v1",
        {
            "commitment_weight": 0.25,
            "projection_lr_multiplier": 1.0,
        },
    )
    provenance["config_digest"] = _semantic_digest(
        "ai-researcher/run-config/v1",
        config,
    )
    provenance["manipulation_status"] = "baseline"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_attempt_spec_from_environment(_environment_for(path))

    assert loaded.payload["proposal"]["change"] is None


def test_attempt_spec_rejects_duplicate_json_object_keys(tmp_path):
    path, _, _ = _write_valid_spec(tmp_path / "raw-evidence")
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace("{", '{"schema_version":2,', 1),
        encoding="utf-8",
    )

    with pytest.raises(AttemptSpecError, match="duplicate JSON field"):
        load_attempt_spec_from_environment(_environment_for(path))


def test_vq_domain_preflight_produces_a_spec_accepted_by_frozen_loader(
    tmp_path,
):
    repo_root = Path(__file__).resolve().parents[2]
    contract_path = (
        repo_root
        / "benchmark/evaluators/one_layer_vq_smoke"
        / "contract.closed_loop_v3.yaml"
    )
    contract = load_evaluation_contract(contract_path)
    policy = contract.adaptive_experiment
    assert policy is not None
    adapter = VQExperimentDomainAdapter(
        task_id=contract.task_id,
        policy=policy,
        contract=contract,
        contract_path=contract_path,
        trusted_sources={
            "protocol.py": (repo_root / "benchmark/real_smoke/one_layer_vq/train.py"),
            "run_training_testing.py": (
                repo_root
                / "benchmark/process/dataset_candidate/vq"
                / "run_training_testing.py"
            ),
            "attempt_spec.py": (
                repo_root / "benchmark/process/dataset_candidate/vq" / "attempt_spec.py"
            ),
        },
        dataset_descriptor={
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
        environment_descriptor={
            "python": "3.11.9",
            "numpy": "2.0",
            "torch": "2.7",
            "torchvision": "0.22",
            "platform_system": "Darwin",
            "platform_machine": "arm64",
            "requested_device": "auto",
            "resolved_device": "cpu",
        },
        command=("python", "run_training_testing.py"),
    )
    request = AdaptiveExperimentRequest(
        run_id="run-1",
        iteration_number=1,
        hypothesis=Hypothesis(
            hypothesis_id="hypothesis-1",
            task_id=contract.task_id,
            statement="Establish the frozen VQ baseline.",
            mechanism="The baseline anchors later Interventions.",
            expected_metric="codebook_utilization",
            metric_direction="maximize",
        ),
        seed=401,
        attempt_cache_path=tmp_path / "iteration-001",
        evidence_dir=tmp_path / "iteration-001/raw-evidence",
        recall_context=None,
        previous=None,
    )

    plan = adapter.prepare(
        adapter.baseline(policy=policy, seed=request.seed),
        request=request,
        project_dir=tmp_path / "project",
        evidence_dir=request.evidence_dir,
    )
    loaded = load_attempt_spec_from_environment(plan.environment)

    assert loaded.path == plan.spec_path
    assert loaded.payload["effective_config"] == plan.preflight.effective_config
    assert loaded.payload["proposal"]["change"] is None
