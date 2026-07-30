from __future__ import annotations

import copy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np

from research_agent.inno.experience.evaluation import (
    AdaptiveExperimentPolicy,
    EvaluationContract,
    evaluator_identity,
)
from research_agent.inno.experience.intervention import (
    InterventionProposal,
    KnobChange,
    semantic_digest,
)
from research_agent.runtime.adaptive_experiment import (
    AdaptiveExperimentRequest,
    DomainExecutionPlan,
    FrozenSourceMismatch,
    InterventionPolicyViolation,
    ManifestMissing,
    ManifestProvenanceMismatch,
    ProcessReceipt,
    PreviousAttemptFeedback,
    ResolvedIntervention,
    TrialPreflight,
    TrialReceipt,
)
from research_agent.runtime.trial_provenance import (
    artifact_ref,
    atomic_write_canonical_json,
    content_digest,
    evidence_payload_digest,
    file_set_digest,
    raw_sha256,
)


_SPEC_PATH_ENV = "AI_RESEARCHER_ATTEMPT_SPEC"
_SPEC_SHA256_ENV = "AI_RESEARCHER_ATTEMPT_SPEC_SHA256"


class VQExperimentDomainAdapter:
    """Resolve and attest one frozen CIFAR-10 SimVQ Experiment Attempt."""

    domain_id = "vq"
    schema_id = "vq.intervention/v1"

    def __init__(
        self,
        *,
        task_id: str,
        policy: AdaptiveExperimentPolicy,
        contract: EvaluationContract,
        contract_path: str | Path,
        trusted_sources: Mapping[str, str | Path],
        dataset_descriptor: Mapping[str, Any],
        environment_descriptor: Mapping[str, Any],
        command: tuple[str, ...],
    ) -> None:
        self.task_id = task_id
        self.policy = policy
        self.contract = contract
        self.contract_path = Path(contract_path).resolve()
        self.trusted_sources = {
            name: Path(path).resolve() for name, path in trusted_sources.items()
        }
        self.dataset_descriptor = copy.deepcopy(dict(dataset_descriptor))
        self.environment_descriptor = copy.deepcopy(dict(environment_descriptor))
        self.command = command
        if set(self.trusted_sources) != set(policy.source_files):
            raise FrozenSourceMismatch(
                "trusted source set does not match the Intervention Catalog"
            )
        if contract.task_id != task_id or contract.adaptive_experiment != policy:
            raise InterventionPolicyViolation(
                "VQ Domain Adapter contract and policy do not match"
            )

    def baseline(
        self,
        *,
        policy: AdaptiveExperimentPolicy,
        seed: int,
    ) -> ResolvedIntervention:
        self._require_policy(policy)
        proposal = InterventionProposal(
            domain=self.domain_id,
            schema_id=self.schema_id,
            decision_point=policy.decision_point,
            knob=None,
            target=None,
            cited_knowledge_ids=[],
            expected_primary_metric_direction="unchanged",
            guardrail_risks=[],
            rationale="System-generated Intervention Catalog baseline.",
        )
        effective_knobs = dict(policy.defaults)
        return ResolvedIntervention(
            proposal=proposal,
            changes=[],
            effective_knobs=effective_knobs,
            effective_config=self._effective_config(
                effective_knobs,
                seed=seed,
            ),
            manipulation_status="baseline",
        )

    def resolve(
        self,
        proposal: InterventionProposal,
        *,
        policy: AdaptiveExperimentPolicy,
        previous: PreviousAttemptFeedback,
        seed: int,
    ) -> ResolvedIntervention:
        self._require_policy(policy)
        if (
            proposal.domain != self.domain_id
            or proposal.schema_id != self.schema_id
            or proposal.decision_point != policy.decision_point
        ):
            raise InterventionPolicyViolation(
                "proposal does not target the VQ Intervention decision point"
            )
        knob = proposal.knob
        if knob is None or knob not in policy.knobs:
            raise InterventionPolicyViolation(
                f"proposal selects an unknown VQ knob: {knob!r}"
            )
        target = proposal.target
        if type(target) is not float or target not in policy.knobs[knob].allowed_values:
            raise InterventionPolicyViolation(
                f"target is outside the VQ Intervention Catalog: {knob}={target!r}"
            )
        expected_keys = {
            *policy.fixed_config,
            *policy.knobs,
            "seed",
            "resolved_device",
        }
        if set(previous.effective_config) != expected_keys:
            raise InterventionPolicyViolation(
                "previous feedback is not a complete VQ execution config"
            )
        for name, expected in policy.fixed_config.items():
            if previous.effective_config[name] != expected:
                raise InterventionPolicyViolation(
                    f"previous feedback changed fixed VQ config: {name}"
                )
        if previous.effective_config["seed"] != seed:
            raise InterventionPolicyViolation(
                "VQ seed differs from previous verified feedback"
            )
        if (
            previous.effective_config["resolved_device"]
            != self.environment_descriptor["resolved_device"]
        ):
            raise InterventionPolicyViolation(
                "VQ resolved environment differs from previous verified feedback"
            )
        effective_knobs: dict[str, float] = {}
        for name, knob_policy in policy.knobs.items():
            value = previous.effective_config[name]
            if type(value) is not float or value not in knob_policy.allowed_values:
                raise InterventionPolicyViolation(
                    f"previous feedback has an invalid VQ knob: {name}"
                )
            effective_knobs[name] = value
        from_value = effective_knobs[knob]
        effective_knobs[knob] = target
        status = "no_effect" if target == from_value else "changed"
        return ResolvedIntervention(
            proposal=proposal,
            changes=[
                KnobChange(
                    name=knob,
                    from_value=from_value,
                    to_value=target,
                )
            ],
            effective_knobs=effective_knobs,
            effective_config=self._effective_config(
                effective_knobs,
                seed=seed,
            ),
            manipulation_status=status,
        )

    def prepare(
        self,
        resolved: ResolvedIntervention,
        *,
        request: AdaptiveExperimentRequest,
        project_dir: Path,
        evidence_dir: Path,
    ) -> DomainExecutionPlan:
        project_dir.mkdir(parents=True, exist_ok=True)
        restored_sources = self._restore_sources(project_dir)
        source_digest = file_set_digest(
            "ai-researcher/source-set/v1",
            restored_sources,
        )
        if source_digest != self.policy.expected_source_digest:
            raise FrozenSourceMismatch(
                "restored VQ sources do not match expected_source_digest"
            )
        dataset_descriptor = self._dataset_for_seed(request.seed)
        environment_descriptor = copy.deepcopy(self.environment_descriptor)
        proposal_digest = semantic_digest(
            "ai-researcher/proposal/v1",
            resolved.proposal.model_dump(mode="json"),
        )
        intervention_digest = semantic_digest(
            "ai-researcher/intervention/v1",
            resolved.effective_knobs,
        )
        config_digest = semantic_digest(
            "ai-researcher/run-config/v1",
            resolved.effective_config,
        )
        dataset_digest = semantic_digest(
            "ai-researcher/dataset-plan/v1",
            dataset_descriptor,
        )
        environment_digest = semantic_digest(
            "ai-researcher/environment/v1",
            environment_descriptor,
        )
        contract_digest = content_digest(
            "ai-researcher/contract/v1",
            self.contract_path.read_bytes(),
        )
        evaluator_digest = evaluator_identity(
            self.contract,
            self.contract_path.parent,
        )
        attempt_key = (
            f"{request.run_id}:iteration-{request.iteration_number:03d}"
        )
        change = (
            {
                "name": resolved.changes[0].name,
                "from": resolved.changes[0].from_value,
                "to": resolved.changes[0].to_value,
            }
            if resolved.changes
            else None
        )
        spec = {
            "schema_version": 1,
            "attempt_key": attempt_key,
            "task_id": self.task_id,
            "policy": {
                "id": self.policy.policy_id,
                "version": self.policy.version,
            },
            "proposal": {
                "digest": proposal_digest,
                "record": resolved.proposal.model_dump(mode="json"),
                "change": change,
            },
            "effective_config": resolved.effective_config,
            "descriptors": {
                "dataset": dataset_descriptor,
                "environment": environment_descriptor,
            },
            "provenance": {
                "intervention_digest": intervention_digest,
                "config_digest": config_digest,
                "source_digest": source_digest,
                "dataset_digest": dataset_digest,
                "environment_digest": environment_digest,
                "contract_digest": contract_digest,
                "evaluator_digest": evaluator_digest,
                "manipulation_status": resolved.manipulation_status,
            },
            "required_artifacts": list(self.contract.required_artifacts),
        }
        attempt_spec_digest = semantic_digest(
            "ai-researcher/attempt-spec/v1",
            spec,
        )
        spec_path = evidence_dir / "attempt_spec.json"
        spec_ref = atomic_write_canonical_json(spec_path, spec)
        environment = {
            **os.environ,
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
            _SPEC_PATH_ENV: str(spec_path.resolve()),
            _SPEC_SHA256_ENV: spec_ref.sha256,
        }
        return DomainExecutionPlan(
            preflight=TrialPreflight(
                attempt_key=attempt_key,
                proposal_digest=proposal_digest,
                intervention_digest=intervention_digest,
                config_digest=config_digest,
                source_digest=source_digest,
                dataset_digest=dataset_digest,
                environment_digest=environment_digest,
                contract_digest=contract_digest,
                evaluator_digest=evaluator_digest,
                attempt_spec_digest=attempt_spec_digest,
                effective_config=resolved.effective_config,
                manipulation_status=resolved.manipulation_status,
            ),
            spec_path=spec_path,
            command=self.command,
            cwd=project_dir,
            evidence_dir=evidence_dir,
            environment=environment,
            required_artifacts=tuple(self.contract.required_artifacts),
            immutable_inputs=(
                *(
                    (path, raw_sha256(path.read_bytes()))
                    for path in restored_sources.values()
                ),
                (spec_path, spec_ref.sha256),
            ),
        )

    def collect_receipt(
        self,
        plan: DomainExecutionPlan,
        process: ProcessReceipt | None,
    ) -> TrialReceipt:
        missing = [
            name
            for name in plan.required_artifacts
            if not (plan.evidence_dir / name).is_file()
        ]
        if missing:
            raise ManifestMissing(
                "missing VQ evidence artifacts: " + ", ".join(missing)
            )
        manifest_path = plan.evidence_dir / "evaluation_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            spec = json.loads(plan.spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestProvenanceMismatch(
                "cannot parse VQ manifest or execution envelope"
            ) from exc
        preflight = plan.preflight
        spec_ref = artifact_ref(plan.spec_path)
        if semantic_digest(
            "ai-researcher/attempt-spec/v1",
            spec,
        ) != preflight.attempt_spec_digest:
            raise ManifestProvenanceMismatch(
                "VQ Attempt Spec semantic digest changed after preflight"
            )
        proposal_envelope = spec.get("proposal")
        if not isinstance(proposal_envelope, dict):
            raise ManifestProvenanceMismatch("VQ Attempt Spec proposal is invalid")
        proposal_record = proposal_envelope.get("record")
        if (
            not isinstance(proposal_record, dict)
            or proposal_envelope.get("digest") != preflight.proposal_digest
            or semantic_digest(
                "ai-researcher/proposal/v1",
                proposal_record,
            )
            != preflight.proposal_digest
        ):
            raise ManifestProvenanceMismatch(
                "VQ Attempt Spec proposal digest mismatch"
            )
        if (
            spec.get("effective_config") != preflight.effective_config
            or semantic_digest(
                "ai-researcher/run-config/v1",
                spec.get("effective_config"),
            )
            != preflight.config_digest
        ):
            raise ManifestProvenanceMismatch(
                "VQ Attempt Spec config digest mismatch"
            )
        effective_knobs = {
            name: preflight.effective_config[name] for name in self.policy.knobs
        }
        if semantic_digest(
            "ai-researcher/intervention/v1",
            effective_knobs,
        ) != preflight.intervention_digest:
            raise ManifestProvenanceMismatch(
                "VQ Attempt Spec Intervention digest mismatch"
            )
        expected_spec_provenance = {
            "intervention_digest": preflight.intervention_digest,
            "config_digest": preflight.config_digest,
            "source_digest": preflight.source_digest,
            "dataset_digest": preflight.dataset_digest,
            "environment_digest": preflight.environment_digest,
            "contract_digest": preflight.contract_digest,
            "evaluator_digest": preflight.evaluator_digest,
            "manipulation_status": preflight.manipulation_status,
        }
        if spec.get("provenance") != expected_spec_provenance:
            raise ManifestProvenanceMismatch(
                "VQ Attempt Spec provenance differs from preflight"
            )
        descriptors = spec.get("descriptors")
        if (
            not isinstance(descriptors, dict)
            or set(descriptors) != {"dataset", "environment"}
            or semantic_digest(
                "ai-researcher/dataset-plan/v1",
                descriptors["dataset"],
            )
            != preflight.dataset_digest
            or semantic_digest(
                "ai-researcher/environment/v1",
                descriptors["environment"],
            )
            != preflight.environment_digest
        ):
            raise ManifestProvenanceMismatch(
                "VQ execution descriptors do not match preflight digests"
            )
        if manifest.get("schema_version") != 2:
            raise ManifestProvenanceMismatch("VQ manifest must use schema 2")
        if manifest.get("attempt_spec_sha256") != spec_ref.sha256:
            raise ManifestProvenanceMismatch("VQ manifest Attempt Spec mismatch")
        if manifest.get("task_id") != self.task_id:
            raise ManifestProvenanceMismatch("VQ manifest task mismatch")
        if manifest.get("contract") != {
            "id": self.contract.contract_id,
            "version": self.contract.version,
            "digest": preflight.contract_digest,
        }:
            raise ManifestProvenanceMismatch("VQ manifest contract mismatch")
        expected_provenance = {
            "proposal_digest": preflight.proposal_digest,
            "intervention_digest": preflight.intervention_digest,
            "config_digest": preflight.config_digest,
            "source_digest": preflight.source_digest,
            "dataset_digest": preflight.dataset_digest,
            "environment_digest": preflight.environment_digest,
            "evaluator_digest": preflight.evaluator_digest,
            "manipulation_status": preflight.manipulation_status,
        }
        if manifest.get("provenance") != expected_provenance:
            raise ManifestProvenanceMismatch("VQ manifest provenance mismatch")
        if manifest.get("effective_config") != preflight.effective_config:
            raise ManifestProvenanceMismatch("VQ manifest config mismatch")
        if manifest.get("descriptors") != descriptors:
            raise ManifestProvenanceMismatch("VQ manifest descriptors mismatch")
        proposal = proposal_envelope
        change = proposal["change"]
        expected_intervention = {
            "decision_point": proposal["record"]["decision_point"],
            "knob": change["name"] if change is not None else None,
            "from": change["from"] if change is not None else None,
            "to": change["to"] if change is not None else None,
            "effective_knobs": {
                name: preflight.effective_config[name]
                for name in self.policy.knobs
            },
        }
        if manifest.get("intervention") != expected_intervention:
            raise ManifestProvenanceMismatch("VQ manifest Intervention mismatch")
        base_learning_rate = preflight.effective_config["base_learning_rate"]
        projection_multiplier = preflight.effective_config[
            "projection_lr_multiplier"
        ]
        expected_optimizer = {
            "base_group": "base",
            "base_learning_rate": base_learning_rate,
            "projection_group": "code_projection",
            "projection_learning_rate": (
                float(base_learning_rate) * float(projection_multiplier)
            ),
        }
        if manifest.get("optimizer") != expected_optimizer:
            raise ManifestProvenanceMismatch("VQ manifest optimizer mismatch")
        execution = manifest.get("execution")
        if not isinstance(execution, dict) or execution.get("exit_code") != 0:
            raise ManifestProvenanceMismatch("VQ manifest execution mismatch")
        try:
            started_at = datetime.fromisoformat(execution["started_at"])
            completed_at = datetime.fromisoformat(execution["completed_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestProvenanceMismatch(
                "VQ manifest execution timestamps are invalid"
            ) from exc
        if completed_at < started_at:
            raise ManifestProvenanceMismatch(
                "VQ manifest execution completes before it starts"
            )
        if process is not None:
            tolerance = timedelta(seconds=2)
            if (
                process.exit_code != 0
                or started_at < process.started_at - tolerance
                or completed_at > process.completed_at + tolerance
            ):
                raise ManifestProvenanceMismatch(
                    "VQ manifest execution is outside the executor envelope"
                )
        arrays_path = plan.evidence_dir / "evaluation_arrays.npz"
        try:
            with np.load(arrays_path, allow_pickle=False) as payload:
                arrays = {name: payload[name] for name in payload.files}
        except (OSError, ValueError) as exc:
            raise ManifestProvenanceMismatch(
                "cannot read VQ raw evidence arrays"
            ) from exc
        payload_digest = evidence_payload_digest(arrays)
        if manifest.get("evidence_payload_digest") != payload_digest:
            raise ManifestProvenanceMismatch(
                "VQ evidence payload digest mismatch"
            )
        artifact_refs = [
            artifact_ref(plan.evidence_dir / name)
            for name in plan.required_artifacts
        ]
        return TrialReceipt(
            attempt_spec_ref=spec_ref,
            manifest_ref=artifact_ref(manifest_path),
            artifact_refs=artifact_refs,
            actual_config=preflight.effective_config,
            proposal_digest=preflight.proposal_digest,
            intervention_digest=preflight.intervention_digest,
            config_digest=preflight.config_digest,
            source_digest=preflight.source_digest,
            dataset_digest=preflight.dataset_digest,
            environment_digest=preflight.environment_digest,
            contract_digest=preflight.contract_digest,
            evaluator_digest=preflight.evaluator_digest,
            evidence_payload_digest=payload_digest,
            started_at=started_at,
            completed_at=completed_at,
            exit_code=0,
        )

    def _effective_config(
        self,
        knobs: Mapping[str, Any],
        *,
        seed: int,
    ) -> dict[str, Any]:
        return {
            **self.policy.fixed_config,
            **knobs,
            "seed": seed,
            "resolved_device": self.environment_descriptor["resolved_device"],
        }

    def _dataset_for_seed(self, seed: int) -> dict[str, Any]:
        descriptor = copy.deepcopy(self.dataset_descriptor)
        train_selector = descriptor.get("train_selector")
        if not isinstance(train_selector, dict):
            raise InterventionPolicyViolation(
                "VQ dataset descriptor has no train selector"
            )
        train_selector["seed"] = seed
        return descriptor

    def _restore_sources(self, project_dir: Path) -> dict[str, Path]:
        restored: dict[str, Path] = {}
        for logical_name in self.policy.source_files:
            source = self.trusted_sources[logical_name]
            if not source.is_file():
                raise FrozenSourceMismatch(
                    f"missing trusted VQ source: {logical_name}"
                )
            target = project_dir / logical_name
            target.parent.mkdir(parents=True, exist_ok=True)
            content = source.read_bytes()
            descriptor, temporary_name = tempfile.mkstemp(
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".frozen-restore",
            )
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, target)
            finally:
                temporary = Path(temporary_name)
                if temporary.exists():
                    temporary.unlink()
            if target.read_bytes() != content:
                raise FrozenSourceMismatch(
                    f"restored VQ source differs from template: {logical_name}"
                )
            restored[logical_name] = target
        return restored

    def _require_policy(self, policy: AdaptiveExperimentPolicy) -> None:
        if policy != self.policy:
            raise InterventionPolicyViolation(
                "VQ Domain Adapter received another policy"
            )
