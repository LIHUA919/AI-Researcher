from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from research_agent.inno.experience.evaluation import AdaptiveExperimentPolicy
from research_agent.inno.experience.intervention import (
    InterventionProposal,
    KnobChange,
    semantic_digest,
)
from research_agent.runtime.adaptive_experiment import (
    AdaptiveExperimentRequest,
    DomainExecutionPlan,
    ManifestProvenanceMismatch,
    ProcessReceipt,
    PreviousAttemptFeedback,
    ResolvedIntervention,
    InterventionPolicyViolation,
    TrialPreflight,
    TrialReceipt,
)
from research_agent.runtime.trial_provenance import (
    artifact_ref,
    atomic_write_canonical_json,
    canonical_json_bytes,
    raw_sha256,
)


class SyntheticResponseSurfaceAdapter:
    """A deterministic Domain Adapter for proving the adaptive Interface."""

    domain_id = "synthetic"
    schema_id = "synthetic.response-surface/v1"

    def __init__(
        self,
        *,
        task_id: str,
        policy: AdaptiveExperimentPolicy,
    ) -> None:
        self.task_id = task_id
        self.policy = policy

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
        effective_config = {
            **policy.fixed_config,
            **effective_knobs,
            "seed": seed,
            "device": "cpu",
        }
        return ResolvedIntervention(
            proposal=proposal,
            changes=[],
            effective_knobs=effective_knobs,
            effective_config=effective_config,
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
                "proposal does not target this Domain Adapter decision point"
            )
        knob = proposal.knob
        if knob is None or knob not in policy.knobs:
            raise InterventionPolicyViolation(
                f"proposal selects an unknown mutable knob: {knob!r}"
            )
        target = proposal.target
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            raise InterventionPolicyViolation("numeric knob target must be numeric")
        if float(target) not in policy.knobs[knob].allowed_values:
            raise InterventionPolicyViolation(
                f"target is outside the Intervention Catalog: {knob}={target!r}"
            )
        for name, fixed_value in policy.fixed_config.items():
            if previous.effective_config.get(name) != fixed_value:
                raise InterventionPolicyViolation(
                    f"previous feedback changed fixed config: {name}"
                )
        if previous.effective_config.get("seed") != seed:
            raise InterventionPolicyViolation(
                "Experiment Attempt seed differs from previous verified feedback"
            )
        if previous.effective_config.get("device") != "cpu":
            raise InterventionPolicyViolation(
                "previous verified feedback has another resolved environment"
            )

        effective_knobs: dict[str, int | float] = {}
        for name, knob_policy in policy.knobs.items():
            value = previous.effective_config.get(name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or float(value) not in knob_policy.allowed_values
            ):
                raise InterventionPolicyViolation(
                    f"previous feedback has an invalid mutable knob: {name}"
                )
            effective_knobs[name] = value
        from_value = effective_knobs[knob]
        effective_knobs[knob] = target
        effective_config = dict(previous.effective_config)
        effective_config[knob] = target
        manipulation_status = "no_effect" if target == from_value else "changed"
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
            effective_config=effective_config,
            manipulation_status=manipulation_status,
        )

    def prepare(
        self,
        resolved: ResolvedIntervention,
        *,
        request: AdaptiveExperimentRequest,
        project_dir: Path,
        evidence_dir: Path,
    ) -> DomainExecutionPlan:
        del project_dir
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
        source_digest = self.policy.expected_source_digest
        dataset_digest = semantic_digest(
            "ai-researcher/dataset-plan/v1",
            {
                "dataset_id": "synthetic",
                "samples": self.policy.fixed_config["samples"],
                "seed": request.seed,
                "selector": "synthetic-sequence/v1",
            },
        )
        environment_digest = semantic_digest(
            "ai-researcher/environment/v1",
            {"runtime": "in-memory", "resolved_device": "cpu"},
        )
        contract_digest = semantic_digest(
            "ai-researcher/contract/v1",
            {
                "task_id": self.task_id,
                "policy_id": self.policy.policy_id,
                "policy_version": self.policy.version,
            },
        )
        evaluator_digest = semantic_digest(
            "ai-researcher/evaluator-set/v1",
            {"evaluator": "synthetic-response-surface/v1"},
        )
        attempt_key = (
            f"{request.run_id}:iteration-{request.iteration_number:03d}"
        )
        required_artifacts = (
            "attempt_spec.json",
            "evaluation_manifest.json",
            "evaluation_arrays.npz",
            "run.log",
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
                "change": (
                    {
                        "name": resolved.changes[0].name,
                        "from": resolved.changes[0].from_value,
                        "to": resolved.changes[0].to_value,
                    }
                    if resolved.changes
                    else None
                ),
            },
            "effective_config": resolved.effective_config,
            "descriptors": {
                "dataset": {
                    "dataset_id": "synthetic",
                    "samples": self.policy.fixed_config["samples"],
                    "seed": request.seed,
                    "selector": "synthetic-sequence/v1",
                },
                "environment": {
                    "runtime": "in-memory",
                    "resolved_device": "cpu",
                },
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
            "required_artifacts": list(required_artifacts),
        }
        attempt_spec_digest = semantic_digest(
            "ai-researcher/attempt-spec/v1",
            spec,
        )
        spec_ref = atomic_write_canonical_json(
            evidence_dir / "attempt_spec.json",
            spec,
        )
        preflight = TrialPreflight(
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
        )
        arrays = canonical_json_bytes(
            {
                "score": (
                    float(resolved.effective_config["gain"]) * 2.0
                    + float(resolved.effective_config["bias"])
                )
            }
        )
        evidence_payload_digest = semantic_digest(
            "ai-researcher/evidence-payload/v1",
            {
                "path": "evaluation_arrays.npz",
                "sha256": raw_sha256(arrays),
                "size_bytes": len(arrays),
            },
        )
        manifest = {
            "schema_version": 2,
            "attempt_spec_sha256": spec_ref.sha256,
            "task_id": self.task_id,
            "provenance": {
                "proposal_digest": proposal_digest,
                "intervention_digest": intervention_digest,
                "config_digest": config_digest,
                "source_digest": source_digest,
                "dataset_digest": dataset_digest,
                "environment_digest": environment_digest,
                "contract_digest": contract_digest,
                "evaluator_digest": evaluator_digest,
                "manipulation_status": resolved.manipulation_status,
            },
            "effective_config": resolved.effective_config,
            "descriptors": spec["descriptors"],
            "evidence_payload_digest": evidence_payload_digest,
        }
        return DomainExecutionPlan(
            preflight=preflight,
            spec_path=evidence_dir / "attempt_spec.json",
            command=("__synthetic__",),
            cwd=evidence_dir,
            evidence_dir=evidence_dir,
            environment={},
            required_artifacts=required_artifacts,
            simulated_artifacts={
                "evaluation_manifest.json": canonical_json_bytes(manifest),
                "evaluation_arrays.npz": arrays,
                "run.log": b"synthetic Experiment Attempt completed\n",
            },
            immutable_inputs=((evidence_dir / "attempt_spec.json", spec_ref.sha256),),
        )

    def collect_receipt(
        self,
        plan: DomainExecutionPlan,
        process: ProcessReceipt | None,
    ) -> TrialReceipt:
        if process is not None and process.exit_code != 0:
            raise ManifestProvenanceMismatch(
                f"synthetic process exited with status {process.exit_code}"
            )
        missing = [
            name
            for name in plan.required_artifacts
            if not (plan.evidence_dir / name).is_file()
        ]
        if missing:
            raise ManifestProvenanceMismatch(
                "missing required artifacts: " + ", ".join(missing)
            )
        manifest_path = plan.evidence_dir / "evaluation_manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestProvenanceMismatch("cannot read synthetic manifest") from exc

        preflight = plan.preflight
        spec = json.loads(plan.spec_path.read_text(encoding="utf-8"))
        if semantic_digest(
            "ai-researcher/attempt-spec/v1",
            spec,
        ) != preflight.attempt_spec_digest:
            raise ManifestProvenanceMismatch(
                "synthetic Attempt Spec semantic digest changed after preflight"
            )
        expected_provenance = {
            "proposal_digest": preflight.proposal_digest,
            "intervention_digest": preflight.intervention_digest,
            "config_digest": preflight.config_digest,
            "source_digest": preflight.source_digest,
            "dataset_digest": preflight.dataset_digest,
            "environment_digest": preflight.environment_digest,
            "contract_digest": preflight.contract_digest,
            "evaluator_digest": preflight.evaluator_digest,
            "manipulation_status": preflight.manipulation_status,
        }
        if manifest.get("provenance") != expected_provenance:
            raise ManifestProvenanceMismatch(
                "manifest Trial Provenance does not match preflight"
            )
        if manifest.get("effective_config") != preflight.effective_config:
            raise ManifestProvenanceMismatch(
                "manifest effective config does not match preflight"
            )
        if manifest.get("descriptors") != spec.get("descriptors"):
            raise ManifestProvenanceMismatch(
                "manifest descriptors do not match the execution envelope"
            )
        attempt_spec_ref = artifact_ref(plan.spec_path)
        if manifest.get("attempt_spec_sha256") != attempt_spec_ref.sha256:
            raise ManifestProvenanceMismatch(
                "manifest attempt spec digest does not match execution envelope"
            )
        execution = manifest.get("execution")
        if not isinstance(execution, dict) or execution.get("exit_code") != 0:
            raise ManifestProvenanceMismatch(
                "manifest has no successful execution receipt"
            )
        try:
            started_at = datetime.fromisoformat(execution["started_at"])
            completed_at = datetime.fromisoformat(execution["completed_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestProvenanceMismatch(
                "manifest execution receipt has invalid timestamps"
            ) from exc
        if process is not None and (
            process.started_at != started_at
            or process.completed_at != completed_at
        ):
            raise ManifestProvenanceMismatch(
                "manifest execution receipt does not match the executor"
            )
        artifact_refs = [
            artifact_ref(plan.evidence_dir / name)
            for name in plan.required_artifacts
        ]
        return TrialReceipt(
            attempt_spec_ref=attempt_spec_ref,
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
            evidence_payload_digest=manifest["evidence_payload_digest"],
            started_at=started_at,
            completed_at=completed_at,
            exit_code=0,
        )

    def _require_policy(self, policy: AdaptiveExperimentPolicy) -> None:
        if policy != self.policy:
            raise ValueError("Synthetic Domain Adapter received another policy")
