from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import platform
from typing import Any, Literal

from research_agent.inno.experience import (
    ArtifactRef,
    CommandVerifier,
    EvaluationContract,
    ExperienceLoop,
    ExperienceMode,
    ExperimentAttempt,
    Hypothesis,
    KeywordExperienceRetriever,
    KnowledgeGate,
    LoopOutcome,
    Observation,
    RecallContext,
    RecallRequest,
    RecordNotFoundError,
    RunCompletion,
    SQLiteExperimentLedger,
    evaluator_identity,
    load_evaluation_contract,
    semantic_digest,
)
from research_agent.runtime.master import MasterRuntime
from research_agent.runtime.adaptive_experiment import (
    AdaptiveExperimentResult,
    PreviousAttemptFeedback,
)
from research_agent.runtime.trial_provenance import (
    bind_trial_provenance,
    build_v3_attempt_id,
    build_v3_observation_id,
    content_digest,
    evidence_bundle_digest,
)


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_ref(path: Path) -> ArtifactRef:
    content = path.read_bytes()
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return ArtifactRef(
        path=str(path.resolve()),
        sha256=hashlib.sha256(content).hexdigest(),
        media_type=media_type,
        size_bytes=len(content),
    )


def _tree_digest(root: Path, *, ignored_names: set[str]) -> str:
    entries: list[tuple[str, str]] = []
    if root.is_dir():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            if path.name in ignored_names or ".git" in path.parts:
                continue
            entries.append((str(path.relative_to(root)), _file_ref(path).sha256))
    return _digest(entries)


class ExperienceConfigurationError(ValueError):
    """Raised when an enabled experience mode lacks a required contract."""


class ExperienceRunAdapter:
    """Connect durable experience services to the two research entrypoints."""

    def __init__(
        self,
        *,
        mode: ExperienceMode,
        store_path: str | Path,
        cache_path: str | Path,
        evaluation_contract_path: str | Path | None = None,
        max_iterations: int = 3,
        recall_item_budget: int = 8,
        recall_token_budget: int = 3000,
    ) -> None:
        self.mode = mode
        self.cache_path = Path(cache_path)
        self.max_iterations = max(1, max_iterations)
        self.recall_item_budget = max(0, recall_item_budget)
        self.recall_token_budget = max(0, recall_token_budget)
        self.ledger = (
            SQLiteExperimentLedger(store_path) if self.mode != "off" else None
        )
        self.contract_path = (
            Path(evaluation_contract_path).resolve()
            if evaluation_contract_path is not None
            else None
        )
        self.contract: EvaluationContract | None = None
        self.loop: ExperienceLoop | None = None

        if self.mode in {"record", "closed-loop"}:
            if self.contract_path is None:
                raise ExperienceConfigurationError(
                    "--evaluation-contract is required when experience recording is enabled"
                )
            self.contract = load_evaluation_contract(self.contract_path)
            assert self.ledger is not None
            self.loop = ExperienceLoop(
                ledger=self.ledger,
                retriever=KeywordExperienceRetriever(self.ledger),
                verifier=CommandVerifier(contract_dir=self.contract_path.parent),
                knowledge_gate=KnowledgeGate(
                    domain="runtime",
                    model_family="runtime",
                ),
                evaluation_contract=self.contract,
                mode=self.mode,
                event_sink=self._emit,
            )

    @classmethod
    def from_args(
        cls,
        args: Any,
        *,
        cache_path: str | Path,
    ) -> "ExperienceRunAdapter":
        return cls(
            mode=getattr(args, "experience_mode", "off"),
            store_path=getattr(
                args,
                "experience_store",
                ".ai_researcher/experience.sqlite3",
            ),
            cache_path=cache_path,
            evaluation_contract_path=getattr(args, "evaluation_contract", None),
            max_iterations=getattr(args, "max_loop_iterations", 3),
            recall_item_budget=getattr(args, "recall_item_budget", 8),
            recall_token_budget=getattr(args, "recall_token_budget", 3000),
        )

    @property
    def records_experience(self) -> bool:
        return self.mode in {"record", "closed-loop"}

    @property
    def runs_closed_loop(self) -> bool:
        return self.mode == "closed-loop"

    @property
    def evaluation_evidence_guidance(self) -> str | None:
        if self.contract is None:
            return None
        return self.contract.evidence_instructions

    def before_run(
        self,
        *,
        task_id: str,
        query: str,
        domain: str,
        dataset_id: str,
        model_family: str,
    ) -> RecallContext | None:
        if self.mode == "off":
            return None
        assert self.ledger is not None
        request = RecallRequest(
            query=query,
            task_id=task_id,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            max_items=self.recall_item_budget,
            token_budget=self.recall_token_budget,
        )
        if self.loop is not None:
            return self.loop.before_run(request)
        return KeywordExperienceRetriever(self.ledger).recall(request)

    def verification_check(self, run_id: str):
        if not self.records_experience:
            return None
        assert self.ledger is not None
        return lambda: self.ledger.has_valid_verification(run_id)

    def pending_verification_check(self):
        """Keep a running attempt non-terminal until its evaluator has executed."""

        if not self.records_experience:
            return None
        return lambda: False

    def build_previous_feedback(
        self,
        flow_result: dict[str, Any],
        outcome: LoopOutcome | None,
    ) -> PreviousAttemptFeedback | None:
        """Carry only externally verified V3 state into the next decision."""

        if (
            outcome is None
            or outcome.experience is None
            or outcome.verification is None
        ):
            return None
        adaptive_payload = (flow_result.get("metadata") or {}).get(
            "adaptive_experiment"
        )
        if adaptive_payload is None:
            return None
        try:
            adaptive = AdaptiveExperimentResult.model_validate(adaptive_payload)
        except Exception as exc:
            raise ExperienceConfigurationError(
                "adaptive experiment metadata is not a valid typed result"
            ) from exc
        intervention = adaptive.intervention
        if (
            adaptive.receipt is None
            or intervention.resolved_config is None
            or intervention.config_digest is None
        ):
            return None
        assert self.ledger is not None
        provenance = self.ledger.find_trial_provenance(
            outcome.experience.observation.observation_id
        )
        if (
            provenance is None
            or provenance.intervention_id != intervention.intervention_id
            or provenance.config_digest != intervention.config_digest
        ):
            raise ExperienceConfigurationError(
                "verified adaptive result is missing matching Trial Provenance"
            )
        verification = outcome.verification
        return PreviousAttemptFeedback(
            attempt_id=outcome.experience.attempt.attempt_id,
            intervention_id=intervention.intervention_id,
            config_digest=intervention.config_digest,
            effective_config=intervention.resolved_config,
            verified_metrics=(
                verification.verified_metrics if verification.valid else {}
            ),
            outcome=verification.outcome,
            guardrail_violations=list(verification.violations),
        )

    def after_flow(
        self,
        flow_result: dict[str, Any],
        *,
        project_dir: str | Path,
        run_id: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        seed: int = 0,
    ) -> LoopOutcome | None:
        return self._record_result(
            flow_result,
            project_dir=project_dir,
            run_id=run_id,
            model=model,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            recall_context=recall_context,
            iteration_number=iteration_number,
            seed=seed,
            attempt_status="completed",
            exit_code=0,
            error=None,
        )

    def after_failure(
        self,
        *,
        project_dir: str | Path,
        run_id: str,
        task_id: str,
        query: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        error: Exception,
        seed: int = 0,
    ) -> LoopOutcome | None:
        if (
            self.contract is not None
            and self.contract.adaptive_experiment is not None
        ):
            # The Facade may already have persisted an Intervention or immutable
            # envelope. Without a successful typed receipt there is no truthful
            # Experiment Attempt/Observation to synthesize.
            return None
        failure = {
            "type": type(error).__name__,
            "message": str(error),
        }
        return self._record_result(
            {
                "task_id": task_id,
                "query": query,
                "analysis": f"The research attempt failed: {failure['type']}.",
                "metadata": {
                    "failure_hypothesis": {
                        "task_id": task_id,
                        "statement": query,
                        "conditions": [domain],
                    }
                },
            },
            project_dir=project_dir,
            run_id=run_id,
            model=model,
            domain=domain,
            dataset_id=dataset_id,
            model_family=model_family,
            recall_context=recall_context,
            iteration_number=iteration_number,
            seed=seed,
            attempt_status="failed",
            exit_code=1,
            error=failure,
        )

    def _record_result(
        self,
        flow_result: dict[str, Any],
        *,
        project_dir: str | Path,
        run_id: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        seed: int,
        attempt_status: Literal["completed", "failed"],
        exit_code: int,
        error: dict[str, Any] | None,
    ) -> LoopOutcome | None:
        if not self.records_experience:
            return None
        assert self.loop is not None
        assert self.contract is not None

        metadata = flow_result.get("metadata") or {}
        if self.contract.adaptive_experiment is not None:
            adaptive_payload = metadata.get("adaptive_experiment")
            if adaptive_payload is None:
                raise ExperienceConfigurationError(
                    "schema 2 adaptive runs require typed adaptive experiment metadata"
                )
            try:
                adaptive = AdaptiveExperimentResult.model_validate(
                    adaptive_payload
                )
            except Exception as exc:
                raise ExperienceConfigurationError(
                    "adaptive experiment metadata is invalid"
                ) from exc
            if adaptive.status == "rejected_no_effect":
                self._validate_rejected_adaptive_result(
                    adaptive=adaptive,
                    run_id=run_id,
                    dataset_id=dataset_id,
                    recall_context=recall_context,
                    iteration_number=iteration_number,
                )
                outcome = self.loop.after_intervention_rejection(
                    intervention=adaptive.intervention,
                    reason="manipulation_no_effect",
                )
                self._write_json(
                    self.cache_path / "experience_outcome.json",
                    outcome.model_dump(mode="json"),
                )
                return outcome
            if attempt_status != "completed" or exit_code != 0:
                raise ExperienceConfigurationError(
                    "adaptive execution failures cannot be converted into fake trials"
                )
            return self._record_adaptive_result(
                flow_result=flow_result,
                adaptive=adaptive,
                run_id=run_id,
                model=model,
                domain=domain,
                dataset_id=dataset_id,
                model_family=model_family,
                recall_context=recall_context,
                iteration_number=iteration_number,
                seed=seed,
            )

        project = Path(project_dir).resolve()
        project.mkdir(parents=True, exist_ok=True)
        source_refs = self._artifact_refs(project)
        artifact_time = self._artifact_time(source_refs)
        if "hypothesis" in metadata:
            hypothesis = Hypothesis.model_validate(metadata["hypothesis"])
        else:
            failure_hypothesis = metadata["failure_hypothesis"]
            hypothesis_payload = {
                "task_id": failure_hypothesis["task_id"],
                "statement": failure_hypothesis["statement"],
                "mechanism": "The attempted research execution did not complete.",
                "expected_metric": self.contract.primary_metric.name,
                "metric_direction": self.contract.primary_metric.direction,
                "conditions": failure_hypothesis["conditions"],
                "parent_experience_ids": sorted(
                    {
                        source_id
                        for item in (
                            recall_context.items if recall_context is not None else []
                        )
                        for source_id in item.source_experience_ids
                    }
                ),
                "citations": [
                    item.citation_id
                    for item in (
                        recall_context.items if recall_context is not None else []
                    )
                ],
            }
            hypothesis = Hypothesis(
                hypothesis_id=_digest(hypothesis_payload),
                created_at=artifact_time,
                **hypothesis_payload,
            )
        assert self.ledger is not None
        try:
            existing_hypothesis = self.ledger.get_hypothesis(
                hypothesis.hypothesis_id
            )
        except RecordNotFoundError:
            pass
        else:
            semantic_fields = {"created_at"}
            existing_payload = existing_hypothesis.model_dump(
                mode="json",
                exclude=semantic_fields,
            )
            candidate_payload = hypothesis.model_dump(
                mode="json",
                exclude=semantic_fields,
            )
            if existing_payload != candidate_payload:
                raise ExperienceConfigurationError(
                    "hypothesis ID collision with different semantic content"
                )
            # Hypothesis IDs are semantic hashes. Reuse the first immutable
            # record so repeated control iterations do not differ only by the
            # non-semantic creation timestamp.
            hypothesis = existing_hypothesis
        code_revision = _tree_digest(
            project,
            ignored_names={self.contract.result_file, "experience_observation.json"},
        )
        attempt_id = _digest(
            {
                "run_id": run_id,
                "iteration_number": iteration_number,
                "hypothesis_id": hypothesis.hypothesis_id,
                "code_revision": code_revision,
                "contract": f"{self.contract.contract_id}@{self.contract.version}",
                "recall": recall_context.snapshot_id if recall_context else "off",
                "seed": seed,
                "status": attempt_status,
            }
        )
        attempt = ExperimentAttempt(
            attempt_id=attempt_id,
            run_id=run_id,
            iteration_id=f"{run_id}:{iteration_number}",
            task_id=hypothesis.task_id,
            hypothesis_id=hypothesis.hypothesis_id,
            code_revision=code_revision,
            dataset_id=dataset_id,
            dataset_digest=_digest(dataset_id),
            model_config_digest=_digest(model),
            seed=seed,
            budget={"iterations": self.max_iterations},
            evaluation_contract_id=(
                f"{self.contract.contract_id}@{self.contract.version}"
            ),
            recall_snapshot_id=(
                recall_context.snapshot_id if recall_context is not None else "off"
            ),
            status=attempt_status,
            created_at=artifact_time,
        )
        refs = self._snapshot_artifact_refs(source_refs, attempt_id)
        observation_id = _digest(
            {
                "attempt_id": attempt_id,
                "artifacts": [
                    {"path": Path(ref.path).name, "sha256": ref.sha256}
                    for ref in refs
                ],
                "exit_code": exit_code,
                "error": error,
            }
        )
        observation = Observation(
            observation_id=observation_id,
            attempt_id=attempt_id,
            exit_code=exit_code,
            metrics=self._reported_metrics(project),
            artifact_refs=refs,
            started_at=artifact_time,
            completed_at=artifact_time,
            environment_fingerprint=(
                f"python={platform.python_version()};"
                f"platform={platform.system()}-{platform.machine()}"
            ),
            error=error,
        )
        analysis = self._analysis(flow_result)
        self.loop.knowledge_gate = KnowledgeGate(
            domain=domain,
            model_family=model_family,
        )
        outcome = self.loop.after_run(
            RunCompletion(
                hypothesis=hypothesis,
                attempt=attempt,
                observation=observation,
                analysis=analysis,
                iteration_number=iteration_number,
                max_iterations=self.max_iterations,
            )
        )
        self._write_json(
            self.cache_path / "experience_outcome.json",
            outcome.model_dump(mode="json"),
        )
        return outcome

    def _validate_rejected_adaptive_result(
        self,
        *,
        adaptive: AdaptiveExperimentResult,
        run_id: str,
        dataset_id: str,
        recall_context: RecallContext | None,
        iteration_number: int,
    ) -> None:
        assert self.contract is not None
        assert self.contract_path is not None
        assert self.ledger is not None
        intervention = adaptive.intervention
        preflight = adaptive.preflight
        recall_snapshot_id = (
            recall_context.snapshot_id if recall_context is not None else "off"
        )
        if (
            adaptive.receipt is not None
            or preflight.manipulation_status != "no_effect"
            or intervention.manipulation_status != "no_effect"
            or intervention.previous_intervention_id is None
            or intervention.run_id != run_id
            or intervention.iteration_id
            != f"iteration-{iteration_number:03d}"
            or intervention.task_id != self.contract.task_id
            or intervention.recall_snapshot_id != recall_snapshot_id
            or dataset_id != "cifar10"
            or preflight.proposal_digest != intervention.proposal_digest
            or preflight.intervention_digest
            != intervention.intervention_digest
            or preflight.config_digest != intervention.config_digest
            or preflight.effective_config != intervention.resolved_config
        ):
            raise ExperienceConfigurationError(
                "rejected no-effect result has inconsistent adaptive lineage"
            )
        if (
            preflight.source_digest
            != self.contract.adaptive_experiment.expected_source_digest
            or preflight.contract_digest
            != content_digest(
                "ai-researcher/contract/v1",
                self.contract_path.read_bytes(),
            )
            or preflight.evaluator_digest
            != evaluator_identity(self.contract, self.contract_path.parent)
        ):
            raise ExperienceConfigurationError(
                "rejected no-effect preflight does not match the contract"
            )
        persisted = self.ledger.get_intervention(
            intervention.intervention_id
        )
        previous = self.ledger.get_intervention(
            intervention.previous_intervention_id
        )
        if (
            persisted != intervention
            or previous.intervention_digest
            != intervention.intervention_digest
            or previous.config_digest != intervention.config_digest
        ):
            raise ExperienceConfigurationError(
                "no-effect result does not match persisted prior assignment"
            )

    def _record_adaptive_result(
        self,
        *,
        flow_result: dict[str, Any],
        adaptive: AdaptiveExperimentResult,
        run_id: str,
        model: str,
        domain: str,
        dataset_id: str,
        model_family: str,
        recall_context: RecallContext | None,
        iteration_number: int,
        seed: int,
    ) -> LoopOutcome:
        assert self.contract is not None
        assert self.contract_path is not None
        assert self.loop is not None
        assert self.ledger is not None
        receipt = adaptive.receipt
        if receipt is None:
            raise ExperienceConfigurationError(
                "executed adaptive result is missing its Trial Receipt"
            )
        metadata = flow_result.get("metadata") or {}
        if "hypothesis" not in metadata:
            raise ExperienceConfigurationError(
                "adaptive result is missing its typed Hypothesis"
            )
        hypothesis = Hypothesis.model_validate(metadata["hypothesis"])
        intervention = adaptive.intervention
        preflight = adaptive.preflight
        recall_snapshot_id = (
            recall_context.snapshot_id if recall_context is not None else "off"
        )
        if (
            run_id != intervention.run_id
            or intervention.iteration_id
            != f"iteration-{iteration_number:03d}"
            or hypothesis.hypothesis_id != intervention.hypothesis_id
            or hypothesis.task_id != self.contract.task_id
            or intervention.task_id != self.contract.task_id
            or intervention.recall_snapshot_id != recall_snapshot_id
        ):
            raise ExperienceConfigurationError(
                "adaptive result does not match run, iteration, task, or recall lineage"
            )
        if dataset_id != "cifar10":
            raise ExperienceConfigurationError(
                "adaptive VQ Evaluation Contract requires dataset_id='cifar10'"
            )
        expected_source_digest = (
            self.contract.adaptive_experiment.expected_source_digest
        )
        expected_contract_digest = content_digest(
            "ai-researcher/contract/v1",
            self.contract_path.read_bytes(),
        )
        expected_evaluator_digest = evaluator_identity(
            self.contract,
            self.contract_path.parent,
        )
        shared_digests = (
            "proposal_digest",
            "intervention_digest",
            "config_digest",
            "source_digest",
            "dataset_digest",
            "environment_digest",
            "contract_digest",
            "evaluator_digest",
        )
        if any(
            getattr(preflight, field) != getattr(receipt, field)
            for field in shared_digests
        ):
            raise ExperienceConfigurationError(
                "Trial Receipt digests do not match preflight"
            )
        if (
            preflight.proposal_digest != intervention.proposal_digest
            or preflight.intervention_digest
            != intervention.intervention_digest
            or preflight.config_digest != intervention.config_digest
            or preflight.source_digest != expected_source_digest
            or preflight.contract_digest != expected_contract_digest
            or preflight.evaluator_digest != expected_evaluator_digest
            or preflight.effective_config != receipt.actual_config
            or preflight.effective_config != intervention.resolved_config
            or preflight.manipulation_status
            != intervention.manipulation_status
            or preflight.effective_config.get("seed") != seed
            or preflight.effective_config.get("dataset_id") != "cifar10"
            or receipt.completed_at < receipt.started_at
        ):
            raise ExperienceConfigurationError(
                "adaptive Intervention, preflight, receipt, and contract disagree"
            )
        actual_intervention = self.ledger.get_intervention(
            intervention.intervention_id
        )
        if actual_intervention != intervention:
            raise ExperienceConfigurationError(
                "adaptive result differs from persisted Intervention"
            )

        refs = list(receipt.artifact_refs)
        names = [Path(ref.path).name for ref in refs]
        if (
            len(names) != len(set(names))
            or set(names) != set(self.contract.required_artifacts)
        ):
            raise ExperienceConfigurationError(
                "Trial Receipt must exactly cover required contract artifacts"
            )
        parent_dirs = {Path(ref.path).resolve().parent for ref in refs}
        if len(parent_dirs) != 1:
            raise ExperienceConfigurationError(
                "Trial Receipt artifacts must share one raw-evidence directory"
            )
        for ref in refs:
            path = Path(ref.path).resolve()
            if not path.is_file() or _file_ref(path) != ref:
                raise ExperienceConfigurationError(
                    f"Trial Receipt artifact changed: {path.name}"
                )
        ref_by_name = {Path(ref.path).name: ref for ref in refs}
        if (
            ref_by_name.get("attempt_spec.json") != receipt.attempt_spec_ref
            or ref_by_name.get("evaluation_manifest.json")
            != receipt.manifest_ref
        ):
            raise ExperienceConfigurationError(
                "Trial Receipt envelope or manifest is not in its artifact set"
            )
        try:
            attempt_spec = json.loads(
                Path(receipt.attempt_spec_ref.path).read_text(encoding="utf-8")
            )
            actual_attempt_spec_digest = semantic_digest(
                "ai-researcher/attempt-spec/v1",
                attempt_spec,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ExperienceConfigurationError(
                "Attempt Spec is not finite canonical JSON"
            ) from exc
        if actual_attempt_spec_digest != preflight.attempt_spec_digest:
            raise ExperienceConfigurationError(
                "Attempt Spec semantic digest does not match preflight"
            )

        try:
            existing_hypothesis = self.ledger.get_hypothesis(
                hypothesis.hypothesis_id
            )
        except RecordNotFoundError:
            pass
        else:
            if existing_hypothesis.model_dump(
                mode="json",
                exclude={"created_at"},
            ) != hypothesis.model_dump(mode="json", exclude={"created_at"}):
                raise ExperienceConfigurationError(
                    "hypothesis ID collision with different semantic content"
                )
            hypothesis = existing_hypothesis

        attempt_id = build_v3_attempt_id(
            run_id=run_id,
            iteration_id=intervention.iteration_id,
            task_id=self.contract.task_id,
            hypothesis_id=hypothesis.hypothesis_id,
            intervention_id=intervention.intervention_id,
            seed=seed,
            recall_snapshot_id=recall_snapshot_id,
            intervention_digest=preflight.intervention_digest,
            source_digest=preflight.source_digest,
            config_digest=preflight.config_digest,
            dataset_digest=preflight.dataset_digest,
            environment_digest=preflight.environment_digest,
            contract_digest=preflight.contract_digest,
            evaluator_digest=preflight.evaluator_digest,
        )
        attempt = ExperimentAttempt(
            attempt_id=attempt_id,
            run_id=run_id,
            iteration_id=intervention.iteration_id,
            task_id=self.contract.task_id,
            hypothesis_id=hypothesis.hypothesis_id,
            code_revision=preflight.source_digest,
            dataset_id="cifar10",
            dataset_digest=preflight.dataset_digest,
            model_config_digest=semantic_digest(
                "ai-researcher/research-model/v1",
                {"model": model},
            ),
            seed=seed,
            budget={"iterations": self.max_iterations},
            evaluation_contract_id=(
                f"{self.contract.contract_id}@{self.contract.version}"
            ),
            recall_snapshot_id=recall_snapshot_id,
            status="completed",
            created_at=receipt.started_at,
        )
        snapshot_refs = self._snapshot_artifact_refs(refs, attempt_id)
        observation_id = build_v3_observation_id(
            attempt_id=attempt_id,
            artifact_refs=snapshot_refs,
            exit_code=receipt.exit_code,
            error=None,
        )
        observation = Observation(
            observation_id=observation_id,
            attempt_id=attempt_id,
            exit_code=receipt.exit_code,
            metrics={},
            artifact_refs=snapshot_refs,
            started_at=receipt.started_at,
            completed_at=receipt.completed_at,
            environment_fingerprint=(
                f"environment_digest={preflight.environment_digest}"
            ),
            error=None,
        )
        snapshot_by_name = {
            Path(ref.path).name: ref for ref in snapshot_refs
        }
        provenance = bind_trial_provenance(
            attempt_id=attempt_id,
            observation_id=observation_id,
            intervention=intervention,
            preflight=preflight,
            evidence_digest=evidence_bundle_digest(snapshot_refs),
            execution_envelope_ref=snapshot_by_name["attempt_spec.json"],
            created_at=receipt.completed_at,
        )
        self.loop.knowledge_gate = KnowledgeGate(
            domain=domain,
            model_family=model_family,
        )
        outcome = self.loop.after_run(
            RunCompletion(
                hypothesis=hypothesis,
                attempt=attempt,
                observation=observation,
                analysis=self._analysis(flow_result),
                iteration_number=iteration_number,
                max_iterations=self.max_iterations,
                intervention=intervention,
                trial_provenance=provenance,
                manipulation_status=preflight.manipulation_status,
            )
        )
        self._write_json(
            self.cache_path / "experience_outcome.json",
            outcome.model_dump(mode="json"),
        )
        return outcome

    def finalize_runtime(
        self,
        *,
        run_id: str,
        outcome: LoopOutcome | None,
    ) -> None:
        if not self.records_experience:
            return
        check = self.verification_check(run_id)
        runtime = MasterRuntime(
            str(self.cache_path),
            require_verification_for_completion=True,
            verification_check=check,
        )
        verified = bool(check and check())
        if self.runs_closed_loop and outcome is not None:
            status = {
                "completed": "completed",
                "continue": "running",
                "failed_budget": "failed",
                "invalid": "failed",
                "unverified": "failed",
                "manipulation_failed": "failed",
            }[outcome.action]
        else:
            status = "completed" if verified else "running"
        runtime.write_runtime_status(
            run_id=run_id,
            status=status,
            metadata={
                "experience_mode": self.mode,
                "verification_valid": verified,
                "loop_action": outcome.action if outcome is not None else None,
            },
        )

    def _artifact_refs(self, project: Path) -> list[ArtifactRef]:
        assert self.contract is not None
        refs = [
            _file_ref(project / relative)
            for relative in self.contract.required_artifacts
            if (project / relative).is_file()
        ]
        if refs:
            return refs
        fallback = project / "experience_observation.json"
        self._write_json(
            fallback,
            {"reason": "no required evaluator artifacts were produced"},
        )
        return [_file_ref(fallback)]

    def _snapshot_artifact_refs(
        self,
        refs: list[ArtifactRef],
        attempt_id: str,
    ) -> list[ArtifactRef]:
        evidence_dir = self.cache_path / "attempt_evidence" / attempt_id
        names = [Path(ref.path).name for ref in refs]
        if len(names) != len(set(names)):
            raise ExperienceConfigurationError(
                "evaluation contract artifacts must have unique file names"
            )
        evidence_dir.mkdir(parents=True, exist_ok=True)
        snapshots = []
        for ref in refs:
            source = Path(ref.path).resolve()
            target = evidence_dir / source.name
            content = source.read_bytes()
            if _file_ref(source) != ref:
                raise ExperienceConfigurationError(
                    f"source evidence changed before snapshot: {source.name}"
                )
            if target.is_symlink():
                raise ExperienceConfigurationError(
                    f"immutable attempt evidence cannot be a symlink: "
                    f"{source.name}"
                )
            if target.exists() and (
                not target.is_file() or target.read_bytes() != content
            ):
                raise ExperienceConfigurationError(
                    f"attempt evidence changed for immutable attempt {attempt_id}"
                )
            if not target.exists():
                try:
                    with target.open("xb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                except FileExistsError:
                    if (
                        not target.is_file()
                        or target.read_bytes() != content
                    ):
                        raise ExperienceConfigurationError(
                            "attempt evidence was concurrently changed for "
                            f"immutable attempt {attempt_id}"
                        ) from None
            target.chmod(0o444)
            snapshots.append(_file_ref(target))
        return snapshots

    @staticmethod
    def _artifact_time(refs: list[ArtifactRef]) -> datetime:
        timestamp = max(Path(ref.path).stat().st_mtime for ref in refs)
        return datetime.fromtimestamp(timestamp, timezone.utc)

    @staticmethod
    def _reported_metrics(project: Path) -> dict[str, float]:
        metrics_path = project / "metrics.json"
        if not metrics_path.is_file():
            return {}
        try:
            payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(name): float(value)
            for name, value in payload.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }

    @staticmethod
    def _analysis(flow_result: dict[str, Any]) -> str:
        analysis = flow_result.get("analysis")
        if isinstance(analysis, str) and analysis.strip():
            return analysis.strip()
        final_output = flow_result.get("final_output") or {}
        for key in ("submission_report", "judge_report", "plan_report"):
            value = final_output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return "The run produced evaluator artifacts without a narrative analysis."

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": payload,
        }
        path = self.cache_path / "experience_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            return
        path.write_text(content, encoding="utf-8")
