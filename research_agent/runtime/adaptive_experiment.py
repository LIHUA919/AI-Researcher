from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import secrets
import signal
import stat
import subprocess
import sys
import time
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from research_agent.inno.experience.evaluation import (
    AdaptiveExperimentPolicy,
    load_evaluation_contract,
)
from research_agent.inno.experience.intervention import (
    InterventionProposal,
    InterventionRecord,
    JsonScalar,
    KnobChange,
    semantic_digest,
)
from research_agent.inno.experience.models import (
    ArtifactRef,
    Hypothesis,
    RecallContext,
)
from research_agent.security import redact_sensitive_environment_values
from research_agent.runtime.trial_provenance import (
    ImmutableEnvelopeConflict,
    artifact_ref,
    raw_sha256,
)


Sha256 = str


class AdaptiveExperimentError(RuntimeError):
    """Base class for fail-closed adaptive Experiment Attempt errors."""


class InterventionProposalError(AdaptiveExperimentError):
    pass


class InterventionPolicyViolation(AdaptiveExperimentError):
    pass


class FrozenSourceMismatch(AdaptiveExperimentError):
    pass


class AttemptSpecConflict(AdaptiveExperimentError):
    pass


class AttemptDirectoryNotEmpty(AdaptiveExperimentError):
    pass


class EnvironmentResolutionError(AdaptiveExperimentError):
    pass


class ExperimentExecutionError(AdaptiveExperimentError):
    pass


class ManifestMissing(AdaptiveExperimentError):
    pass


class ManifestProvenanceMismatch(AdaptiveExperimentError):
    pass


class EvidenceCollision(AdaptiveExperimentError):
    pass


class EvaluatorIdentityError(AdaptiveExperimentError):
    pass


class ProvenanceBindingError(AdaptiveExperimentError):
    pass


class _RuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class PreviousAttemptFeedback(_RuntimeModel):
    attempt_id: str
    intervention_id: str
    config_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    effective_config: dict[str, JsonScalar]
    verified_metrics: dict[str, float]
    outcome: Literal["positive", "neutral", "negative", "invalid"]
    guardrail_violations: list[str]

    @field_validator("verified_metrics")
    @classmethod
    def verified_metrics_are_finite(
        cls,
        metrics: dict[str, float],
    ) -> dict[str, float]:
        if any(not math.isfinite(value) for value in metrics.values()):
            raise ValueError("previous verified metrics must be finite")
        return metrics

    @model_validator(mode="after")
    def config_identity_matches(self) -> "PreviousAttemptFeedback":
        expected = semantic_digest(
            "ai-researcher/run-config/v1",
            self.effective_config,
        )
        if self.config_digest != expected:
            raise ValueError("previous config digest does not match effective config")
        return self


class AdaptiveExperimentRequest(_RuntimeModel):
    run_id: str = Field(min_length=1)
    iteration_number: int = Field(strict=True, ge=1)
    hypothesis: Hypothesis
    seed: int = Field(strict=True, ge=0, lt=2**63)
    attempt_cache_path: Path
    evidence_dir: Path
    recall_context: RecallContext | None
    previous: PreviousAttemptFeedback | None


class TrialPreflight(_RuntimeModel):
    attempt_key: str
    proposal_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    intervention_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    config_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    source_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    environment_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    contract_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_spec_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    effective_config: dict[str, JsonScalar]
    manipulation_status: Literal["baseline", "changed", "no_effect"]

    @model_validator(mode="after")
    def config_identity_matches(self) -> "TrialPreflight":
        expected = semantic_digest(
            "ai-researcher/run-config/v1",
            self.effective_config,
        )
        if self.config_digest != expected:
            raise ValueError("preflight config digest does not match effective config")
        return self


class TrialReceipt(_RuntimeModel):
    attempt_spec_ref: ArtifactRef
    manifest_ref: ArtifactRef
    artifact_refs: list[ArtifactRef]
    actual_config: dict[str, JsonScalar]
    proposal_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    intervention_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    config_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    source_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    environment_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    contract_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_payload_digest: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    exit_code: Literal[0]

    @model_validator(mode="after")
    def validate_receipt(self) -> "TrialReceipt":
        if self.completed_at < self.started_at:
            raise ValueError("Trial Receipt completes before it starts")
        paths = [ref.path for ref in self.artifact_refs]
        names = [Path(path).name for path in paths]
        if len(paths) != len(set(paths)) or len(names) != len(set(names)):
            raise ValueError("Trial Receipt artifact refs must be unique")
        by_path = {ref.path: ref for ref in self.artifact_refs}
        for required in (self.attempt_spec_ref, self.manifest_ref):
            if by_path.get(required.path) != required:
                raise ValueError(
                    "Trial Receipt envelope and manifest must be artifact refs"
                )
        expected_config_digest = semantic_digest(
            "ai-researcher/run-config/v1",
            self.actual_config,
        )
        if self.config_digest != expected_config_digest:
            raise ValueError("Trial Receipt config digest does not match actual config")
        return self


class AdaptiveExperimentResult(_RuntimeModel):
    status: Literal["executed", "executed_no_effect", "rejected_no_effect"]
    intervention: InterventionRecord
    preflight: TrialPreflight
    receipt: TrialReceipt | None

    @model_validator(mode="after")
    def validate_disposition(self) -> "AdaptiveExperimentResult":
        manipulation = self.preflight.manipulation_status
        if self.intervention.manipulation_status != manipulation:
            raise ValueError("result Intervention and preflight dispositions differ")
        if (
            self.intervention.proposal_digest
            != self.preflight.proposal_digest
            or self.intervention.intervention_digest
            != self.preflight.intervention_digest
            or self.intervention.config_digest
            != self.preflight.config_digest
            or self.intervention.resolved_config
            != self.preflight.effective_config
        ):
            raise ValueError(
                "result Intervention and preflight digests differ"
            )
        if self.status == "rejected_no_effect":
            if manipulation != "no_effect" or self.receipt is not None:
                raise ValueError(
                    "rejected_no_effect requires no-effect preflight and no receipt"
                )
        elif self.status == "executed_no_effect":
            if manipulation != "no_effect" or self.receipt is None:
                raise ValueError(
                    "executed_no_effect requires no-effect preflight and receipt"
                )
        elif manipulation not in {"baseline", "changed"} or self.receipt is None:
            raise ValueError(
                "executed requires baseline/changed preflight and a receipt"
            )
        if self.receipt is not None:
            digest_fields = (
                "proposal_digest",
                "intervention_digest",
                "config_digest",
                "source_digest",
                "dataset_digest",
                "environment_digest",
                "contract_digest",
                "evaluator_digest",
            )
            mismatched = [
                field
                for field in digest_fields
                if getattr(self.receipt, field) != getattr(self.preflight, field)
            ]
            if mismatched:
                raise ValueError(
                    "Trial Receipt differs from preflight: " + mismatched[0]
                )
            if self.receipt.actual_config != self.preflight.effective_config:
                raise ValueError("Trial Receipt actual config differs from preflight")
        return self


class BaselinePreparationResult(_RuntimeModel):
    intervention: InterventionRecord
    preflight: TrialPreflight
    attempt_spec_ref: ArtifactRef


class InterventionPlanningContext(_RuntimeModel):
    hypothesis: Hypothesis
    policy: AdaptiveExperimentPolicy
    previous: PreviousAttemptFeedback
    recall_context: RecallContext | None


class ResolvedIntervention(_RuntimeModel):
    proposal: InterventionProposal
    changes: list[KnobChange]
    effective_knobs: dict[str, JsonScalar]
    effective_config: dict[str, JsonScalar]
    manipulation_status: Literal["baseline", "changed", "no_effect"]


@dataclass(frozen=True)
class DomainExecutionPlan:
    preflight: TrialPreflight
    spec_path: Path
    command: tuple[str, ...]
    cwd: Path
    evidence_dir: Path
    environment: dict[str, str]
    required_artifacts: tuple[str, ...]
    simulated_artifacts: dict[str, bytes] | None = None
    immutable_inputs: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True)
class _PreparedAdaptiveExperiment:
    resolved: ResolvedIntervention
    plan: DomainExecutionPlan
    intervention: InterventionRecord


class ProcessReceipt(_RuntimeModel):
    started_at: datetime
    completed_at: datetime
    exit_code: int


class InterventionPlanner(Protocol):
    async def propose(
        self,
        context: InterventionPlanningContext,
    ) -> InterventionProposal: ...


class ExperimentDomainAdapter(Protocol):
    domain_id: str
    schema_id: str

    def baseline(
        self,
        *,
        policy: AdaptiveExperimentPolicy,
        seed: int,
    ) -> ResolvedIntervention: ...

    def resolve(
        self,
        proposal: InterventionProposal,
        *,
        policy: AdaptiveExperimentPolicy,
        previous: PreviousAttemptFeedback,
        seed: int,
    ) -> ResolvedIntervention: ...

    def prepare(
        self,
        resolved: ResolvedIntervention,
        *,
        request: AdaptiveExperimentRequest,
        project_dir: Path,
        evidence_dir: Path,
    ) -> DomainExecutionPlan: ...

    def collect_receipt(
        self,
        plan: DomainExecutionPlan,
        process: ProcessReceipt | None,
    ) -> TrialReceipt: ...


class ExecutionAdapter(Protocol):
    def execute(self, plan: DomainExecutionPlan) -> ProcessReceipt: ...


class InterventionSink(Protocol):
    def append_intervention(self, record: InterventionRecord) -> None: ...
    def get_intervention(self, intervention_id: str) -> InterventionRecord: ...
    def list_interventions(self, run_id: str) -> list[InterventionRecord]: ...


def _verify_immutable_inputs(plan: DomainExecutionPlan) -> None:
    for path, expected_sha256 in plan.immutable_inputs:
        try:
            actual_sha256 = raw_sha256(path.read_bytes())
        except OSError as exc:
            if path == plan.spec_path:
                raise AttemptSpecConflict(
                    "execution envelope disappeared before execution"
                ) from exc
            raise FrozenSourceMismatch(
                f"frozen source disappeared before execution: {path.name}"
            ) from exc
        if actual_sha256 != expected_sha256:
            if path == plan.spec_path:
                raise AttemptSpecConflict(
                    "execution envelope changed after preflight"
                )
            raise FrozenSourceMismatch(
                f"frozen source changed after preflight: {path.name}"
            )


def _has_symlink_component(path: Path) -> bool:
    absolute = path if path.is_absolute() else Path.cwd() / path
    return any(
        candidate.is_symlink()
        for candidate in (absolute, *absolute.parents)
    )


@dataclass(frozen=True)
class AdaptiveExperimentBuildConfig:
    project_dir: Path
    contract_path: Path
    ledger: InterventionSink
    execution_timeout_seconds: float = 7200.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_dir", Path(self.project_dir).resolve())
        object.__setattr__(self, "contract_path", Path(self.contract_path).resolve())
        if (
            not math.isfinite(self.execution_timeout_seconds)
            or self.execution_timeout_seconds <= 0
        ):
            raise ValueError("execution timeout must be finite and positive")


class InMemoryExecutionAdapter:
    """Execute a prepared deterministic plan without a subprocess."""

    def execute(self, plan: DomainExecutionPlan) -> ProcessReceipt:
        _verify_immutable_inputs(plan)
        started_at = datetime.now(timezone.utc)
        if plan.simulated_artifacts is None:
            raise ExperimentExecutionError("plan has no in-memory execution payload")
        manifest_content = plan.simulated_artifacts.get("evaluation_manifest.json")
        for logical_name, content in plan.simulated_artifacts.items():
            if logical_name == "evaluation_manifest.json":
                continue
            path = plan.evidence_dir / logical_name
            if path.exists():
                raise EvidenceCollision(f"execution artifact already exists: {logical_name}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        completed_at = datetime.now(timezone.utc)
        if manifest_content is not None:
            manifest_path = plan.evidence_dir / "evaluation_manifest.json"
            if manifest_path.exists():
                raise EvidenceCollision(
                    "execution artifact already exists: evaluation_manifest.json"
                )
            manifest = json.loads(manifest_content)
            manifest["execution"] = {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "exit_code": 0,
            }
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ),
                encoding="utf-8",
            )
        return ProcessReceipt(
            started_at=started_at,
            completed_at=completed_at,
            exit_code=0,
        )


def _process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_tree(
    process: subprocess.Popen[str],
    *,
    grace_seconds: float = 0.25,
) -> None:
    if os.name != "posix":
        process.terminate()
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)
        return

    process_group_id = process.pid
    try:
        os.killpg(process_group_id, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace_seconds
    while _process_group_exists(process_group_id) and time.monotonic() < deadline:
        process.poll()
        time.sleep(0.01)
    if _process_group_exists(process_group_id):
        try:
            os.killpg(process_group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.0)


def _redact_existing_evidence_log(
    evidence_dir: Path,
    logical_name: str,
    environment: dict[str, str],
    *,
    content_if_missing: str | None = None,
) -> bool:
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        directory_descriptor = os.open(evidence_dir, directory_flags)
    except OSError as exc:
        raise EvidenceCollision(
            f"evidence directory is not a regular non-symlink directory: {evidence_dir}"
        ) from exc

    temporary_name: str | None = None
    try:
        opened_stat: os.stat_result | None
        try:
            path_stat = os.stat(
                logical_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if content_if_missing is None:
                return False
            opened_stat = None
            original_content = content_if_missing.encode("utf-8")
        else:
            if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(
                path_stat.st_mode
            ):
                raise EvidenceCollision(
                    "execution log must be a regular non-symlink file: "
                    f"{logical_name}"
                )
            try:
                log_descriptor = os.open(
                    logical_name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
            except OSError as exc:
                raise EvidenceCollision(
                    f"execution log could not be opened safely: {logical_name}"
                ) from exc
            try:
                opened_stat = os.fstat(log_descriptor)
                if (
                    not stat.S_ISREG(opened_stat.st_mode)
                    or (opened_stat.st_dev, opened_stat.st_ino)
                    != (path_stat.st_dev, path_stat.st_ino)
                ):
                    raise EvidenceCollision(
                        f"execution log changed while opening: {logical_name}"
                    )
                with os.fdopen(log_descriptor, "rb", closefd=False) as stream:
                    original_content = stream.read()
            finally:
                os.close(log_descriptor)

        redacted_text = redact_sensitive_environment_values(
            original_content.decode("utf-8", errors="replace"),
            environment,
        )
        redacted_content = redacted_text.encode("utf-8")
        for _ in range(128):
            candidate = f".{logical_name}.{secrets.token_hex(8)}.tmp"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=directory_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise EvidenceCollision(
                f"could not reserve temporary execution log: {logical_name}"
            )
        with os.fdopen(temporary_descriptor, "wb") as stream:
            stream.write(redacted_content)
            stream.flush()
            os.fsync(stream.fileno())
            mode = (
                stat.S_IMODE(opened_stat.st_mode) & 0o666
                if opened_stat is not None
                else 0o600
            )
            os.fchmod(stream.fileno(), mode or 0o400)

        if opened_stat is None:
            try:
                os.link(
                    temporary_name,
                    logical_name,
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as exc:
                raise EvidenceCollision(
                    f"execution log appeared before atomic creation: {logical_name}"
                ) from exc
            os.unlink(temporary_name, dir_fd=directory_descriptor)
        else:
            current_stat = os.stat(
                logical_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                stat.S_ISLNK(current_stat.st_mode)
                or not stat.S_ISREG(current_stat.st_mode)
                or (current_stat.st_dev, current_stat.st_ino)
                != (opened_stat.st_dev, opened_stat.st_ino)
            ):
                raise EvidenceCollision(
                    f"execution log changed before atomic redaction: {logical_name}"
                )
            os.replace(
                temporary_name,
                logical_name,
                src_dir_fd=directory_descriptor,
                dst_dir_fd=directory_descriptor,
            )
        temporary_name = None
        os.fsync(directory_descriptor)

        sealed_descriptor = os.open(
            logical_name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory_descriptor,
        )
        try:
            with os.fdopen(sealed_descriptor, "rb", closefd=False) as stream:
                if stream.read() != redacted_content:
                    raise EvidenceCollision(
                        f"execution log changed after atomic redaction: {logical_name}"
                    )
        finally:
            os.close(sealed_descriptor)
        return True
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
            except FileNotFoundError:
                pass
        os.close(directory_descriptor)


class LocalSubprocessExecutionAdapter:
    """Execute a prepared plan as a local subprocess."""

    def __init__(self, *, timeout_seconds: float = 7200.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("execution timeout must be positive")
        self.timeout_seconds = timeout_seconds

    def execute(self, plan: DomainExecutionPlan) -> ProcessReceipt:
        _verify_immutable_inputs(plan)
        started_at = datetime.now(timezone.utc)
        process = subprocess.Popen(
            plan.command,
            cwd=plan.cwd,
            env=plan.environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=os.name == "posix",
        )
        try:
            stdout, stderr = process.communicate(
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_process_tree(process)
            stdout, stderr = process.communicate()
            safe_output = redact_sensitive_environment_values(
                (stdout or "") + (stderr or ""),
                plan.environment,
            )
            _redact_existing_evidence_log(
                plan.evidence_dir,
                "executor.log",
                plan.environment,
                content_if_missing=safe_output,
            )
            raise ExperimentExecutionError(
                f"Experiment Attempt exceeded {self.timeout_seconds:g} seconds"
            ) from exc
        completed_at = datetime.now(timezone.utc)
        safe_output = redact_sensitive_environment_values(
            stdout + stderr,
            plan.environment,
        )
        if process.returncode != 0:
            _redact_existing_evidence_log(
                plan.evidence_dir,
                "executor.log",
                plan.environment,
                content_if_missing=safe_output,
            )
            raise ExperimentExecutionError(
                f"Experiment Attempt exited with status {process.returncode}"
            )
        _redact_existing_evidence_log(
            plan.evidence_dir,
            "run.log",
            plan.environment,
            content_if_missing=safe_output,
        )
        _redact_existing_evidence_log(
            plan.evidence_dir,
            "executor.log",
            plan.environment,
        )
        return ProcessReceipt(
            started_at=started_at,
            completed_at=completed_at,
            exit_code=process.returncode,
        )


class AdaptiveExperimentRunner:
    """Run one governed Intervention behind a single deep Interface."""

    def __init__(
        self,
        *,
        project_dir: str | Path,
        task_id: str,
        policy: AdaptiveExperimentPolicy,
        planner: InterventionPlanner,
        domain: ExperimentDomainAdapter,
        executor: ExecutionAdapter,
        intervention_sink: InterventionSink,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.task_id = task_id
        self.policy = policy
        self.planner = planner
        self.domain = domain
        self.executor = executor
        self.intervention_sink = intervention_sink

    async def run(
        self,
        request: AdaptiveExperimentRequest,
    ) -> AdaptiveExperimentResult:
        prepared = await self._prepare(request)
        resolved = prepared.resolved
        plan = prepared.plan
        intervention = prepared.intervention
        evidence_dir = request.evidence_dir
        names_after_prepare = {path.name for path in evidence_dir.iterdir()}
        required = set(plan.required_artifacts)
        if required.issubset(names_after_prepare):
            receipt = self.domain.collect_receipt(plan, None)
            return AdaptiveExperimentResult(
                status=self._executed_status(resolved),
                intervention=intervention,
                preflight=plan.preflight,
                receipt=receipt,
            )
        partial_evidence = names_after_prepare - {"attempt_spec.json"}
        if partial_evidence:
            raise EvidenceCollision(
                "Experiment Attempt has partial evidence: "
                + ", ".join(sorted(partial_evidence))
            )
        if (
            resolved.manipulation_status == "no_effect"
            and self.policy.no_op_policy == "reject_before_execution"
        ):
            return AdaptiveExperimentResult(
                status="rejected_no_effect",
                intervention=intervention,
                preflight=plan.preflight,
                receipt=None,
            )
        process = self.executor.execute(plan)
        receipt = self.domain.collect_receipt(plan, process)
        return AdaptiveExperimentResult(
            status=self._executed_status(resolved),
            intervention=intervention,
            preflight=plan.preflight,
            receipt=receipt,
        )

    async def prepare_baseline(
        self,
        request: AdaptiveExperimentRequest,
    ) -> BaselinePreparationResult:
        """Persist and attest a baseline without starting an Experiment Attempt."""

        if request.iteration_number != 1 or request.previous is not None:
            raise InterventionPolicyViolation(
                "preflight-only preparation is restricted to the baseline"
            )
        prepared = await self._prepare(request)
        return BaselinePreparationResult(
            intervention=prepared.intervention,
            preflight=prepared.plan.preflight,
            attempt_spec_ref=artifact_ref(prepared.plan.spec_path),
        )

    async def _prepare(
        self,
        request: AdaptiveExperimentRequest,
    ) -> _PreparedAdaptiveExperiment:
        self._validate_request(request)
        evidence_dir = request.evidence_dir
        names_before = (
            {path.name for path in evidence_dir.iterdir()}
            if evidence_dir.exists()
            else set()
        )
        if names_before and "attempt_spec.json" not in names_before:
            raise AttemptDirectoryNotEmpty(
                "Experiment Attempt evidence directory has no resumable "
                f"execution envelope: {evidence_dir}"
            )
        evidence_dir.mkdir(parents=True, exist_ok=True)

        existing = self._existing_intervention(request)
        if request.iteration_number == 1:
            resolved = self.domain.baseline(policy=self.policy, seed=request.seed)
        elif existing is not None:
            assert request.previous is not None
            resolved = self.domain.resolve(
                existing.proposal,
                policy=self.policy,
                previous=request.previous,
                seed=request.seed,
            )
        else:
            assert request.previous is not None
            proposal = await self.planner.propose(
                InterventionPlanningContext(
                    hypothesis=request.hypothesis,
                    policy=self.policy,
                    previous=request.previous,
                    recall_context=request.recall_context,
                )
            )
            self._validate_proposal_citations(proposal, request.recall_context)
            resolved = self.domain.resolve(
                proposal,
                policy=self.policy,
                previous=request.previous,
                seed=request.seed,
            )
        try:
            plan = self.domain.prepare(
                resolved,
                request=request,
                project_dir=self.project_dir,
                evidence_dir=evidence_dir,
            )
        except ImmutableEnvelopeConflict as exc:
            raise AttemptSpecConflict(
                "existing execution envelope differs from this Experiment Attempt"
            ) from exc
        intervention = self._intervention_record(
            request,
            resolved,
            plan.preflight,
            existing=existing,
        )
        self.intervention_sink.append_intervention(intervention)
        return _PreparedAdaptiveExperiment(
            resolved=resolved,
            plan=plan,
            intervention=intervention,
        )

    def _validate_request(self, request: AdaptiveExperimentRequest) -> None:
        if request.hypothesis.task_id != self.task_id:
            raise InterventionPolicyViolation(
                "Hypothesis task does not match the Evaluation Contract task"
            )
        if (request.iteration_number == 1) != (request.previous is None):
            raise InterventionPolicyViolation(
                "previous feedback must be absent exactly for the first Experiment Attempt"
            )
        expected_iteration_dir = (
            f"iteration-{request.iteration_number:03d}"
        )
        if (
            request.attempt_cache_path.name != expected_iteration_dir
            or request.attempt_cache_path.parent.name != "attempts"
        ):
            raise InterventionPolicyViolation(
                "attempt_cache_path must identify the iteration-specific "
                "attempt cache"
            )
        if (
            ".." in request.attempt_cache_path.parts
            or ".." in request.evidence_dir.parts
            or _has_symlink_component(request.attempt_cache_path)
            or _has_symlink_component(request.evidence_dir)
            or request.evidence_dir.resolve(strict=False)
            != (
                request.attempt_cache_path.resolve(strict=False)
                / "raw-evidence"
            )
        ):
            raise InterventionPolicyViolation(
                "evidence_dir must be inside the authorized attempt cache"
            )
        if request.previous is not None:
            expected_digest = semantic_digest(
                "ai-researcher/run-config/v1",
                request.previous.effective_config,
            )
            if request.previous.config_digest != expected_digest:
                raise ProvenanceBindingError(
                    "previous verified config does not match its config digest"
                )
            try:
                previous = self.intervention_sink.get_intervention(
                    request.previous.intervention_id
                )
            except (AttributeError, LookupError) as exc:
                raise ProvenanceBindingError(
                    "previous feedback has no persisted Intervention"
                ) from exc
            expected_iteration_id = (
                f"iteration-{request.iteration_number - 1:03d}"
            )
            try:
                expected_intervention_digest = semantic_digest(
                    "ai-researcher/intervention/v1",
                    {
                        name: request.previous.effective_config[name]
                        for name in self.policy.knobs
                    },
                )
            except KeyError as exc:
                raise ProvenanceBindingError(
                    "previous feedback is missing an intervention knob"
                ) from exc
            if (
                previous.run_id != request.run_id
                or previous.iteration_id != expected_iteration_id
                or previous.task_id != self.task_id
                or previous.manipulation_status == "rejected"
                or previous.resolved_config
                != request.previous.effective_config
                or previous.config_digest != request.previous.config_digest
                or previous.intervention_digest
                != expected_intervention_digest
            ):
                raise ProvenanceBindingError(
                    "previous feedback does not match the adjacent persisted "
                    "Intervention lineage"
                )

    def _intervention_record(
        self,
        request: AdaptiveExperimentRequest,
        resolved: ResolvedIntervention,
        preflight: TrialPreflight,
        *,
        existing: InterventionRecord | None,
    ) -> InterventionRecord:
        proposal_digest = semantic_digest(
            "ai-researcher/proposal/v1",
            resolved.proposal.model_dump(mode="json"),
        )
        intervention_id = semantic_digest(
            "ai-researcher/intervention-record-id/v1",
            {
                "run_id": request.run_id,
                "iteration_number": request.iteration_number,
                "proposal_digest": proposal_digest,
                "manipulation_status": resolved.manipulation_status,
                "intervention_digest": preflight.intervention_digest,
                "config_digest": preflight.config_digest,
            },
        )
        candidate = InterventionRecord(
            intervention_id=intervention_id,
            run_id=request.run_id,
            iteration_id=f"iteration-{request.iteration_number:03d}",
            task_id=self.task_id,
            hypothesis_id=request.hypothesis.hypothesis_id,
            recall_snapshot_id=(
                request.recall_context.snapshot_id
                if request.recall_context is not None
                else "off"
            ),
            previous_intervention_id=(
                request.previous.intervention_id
                if request.previous is not None
                else None
            ),
            proposal=resolved.proposal,
            proposal_digest=proposal_digest,
            resolved_config=resolved.effective_config,
            config_digest=preflight.config_digest,
            intervention_digest=preflight.intervention_digest,
            manipulation_status=resolved.manipulation_status,
            violations=[],
            created_at=(
                existing.created_at
                if existing is not None
                else request.hypothesis.created_at
            ),
        )
        if existing is not None and candidate != existing:
            raise ProvenanceBindingError(
                "persisted Intervention differs from the reconstructed decision"
            )
        return candidate

    def _validate_proposal_citations(
        self,
        proposal: InterventionProposal,
        recall_context: RecallContext | None,
    ) -> None:
        recalled_ids = {
            item.knowledge_id
            for item in (recall_context.items if recall_context is not None else [])
        }
        unknown = [
            knowledge_id
            for knowledge_id in proposal.cited_knowledge_ids
            if knowledge_id not in recalled_ids
        ]
        if unknown:
            raise InterventionProposalError(
                "proposal cited knowledge not present in the Recall Context: "
                + unknown[0]
            )

    def _existing_intervention(
        self,
        request: AdaptiveExperimentRequest,
    ) -> InterventionRecord | None:
        list_interventions = getattr(
            self.intervention_sink,
            "list_interventions",
            None,
        )
        if list_interventions is None:
            return None
        iteration_id = f"iteration-{request.iteration_number:03d}"
        return next(
            (
                record
                for record in list_interventions(request.run_id)
                if record.iteration_id == iteration_id
            ),
            None,
        )

    def _executed_status(
        self,
        resolved: ResolvedIntervention,
    ) -> Literal["executed", "executed_no_effect"]:
        return (
            "executed_no_effect"
            if resolved.manipulation_status == "no_effect"
            else "executed"
        )


def build_adaptive_experiment_runner(
    config: AdaptiveExperimentBuildConfig,
    *,
    planner: InterventionPlanner,
    executor: ExecutionAdapter | None = None,
) -> AdaptiveExperimentRunner:
    """Compose the production VQ adaptive-experiment Module."""

    from research_agent.runtime.domain_adapters.vq import (
        VQExperimentDomainAdapter,
    )
    from research_agent.runtime.trial_provenance import file_set_digest

    contract = load_evaluation_contract(config.contract_path)
    if contract.schema_version != 2 or contract.adaptive_experiment is None:
        raise InterventionPolicyViolation(
            "Adaptive Experiment runner requires a schema-2 adaptive contract"
        )
    policy = contract.adaptive_experiment
    repository_root = Path(__file__).resolve().parents[2]
    trusted_sources = {
        "protocol.py": (
            repository_root / "benchmark/real_smoke/one_layer_vq/train.py"
        ),
        "run_training_testing.py": (
            repository_root
            / "benchmark/process/dataset_candidate/vq/run_training_testing.py"
        ),
        "attempt_spec.py": (
            repository_root
            / "benchmark/process/dataset_candidate/vq/attempt_spec.py"
        ),
    }
    actual_source_digest = file_set_digest(
        "ai-researcher/source-set/v1",
        trusted_sources,
    )
    if actual_source_digest != policy.expected_source_digest:
        raise FrozenSourceMismatch(
            "trusted VQ templates do not match contract expected_source_digest"
        )
    archive = (
        repository_root
        / "benchmark/process/dataset_candidate/vq/cifar-10-python.tar.gz"
    )
    if not archive.is_file():
        raise InterventionPolicyViolation(
            "official CIFAR-10 archive is unavailable for Trial Provenance"
        )
    archive_sha256 = _sha256_file(archive)
    requested_device = policy.fixed_config.get("device_policy")
    if not isinstance(requested_device, str):
        raise InterventionPolicyViolation(
            "VQ fixed config must declare a device_policy"
        )
    resolved_device = _resolve_torch_device(requested_device)
    dataset_descriptor = {
        "dataset_id": "cifar10",
        "archive_sha256": archive_sha256,
        "source": "torchvision",
        "train_split": policy.fixed_config["train_split"],
        "test_split": policy.fixed_config["test_split"],
        "train_selector": {
            "name": "torch_randperm_without_replacement",
            "version": "1",
            "count": policy.fixed_config["train_samples"],
        },
        "test_selector": {
            "name": "canonical_prefix",
            "version": "1",
            "count": policy.fixed_config["test_samples"],
        },
        "transform": {
            "name": "torchvision.transforms.ToTensor",
            "version": "1",
        },
    }
    environment_descriptor = {
        "python": platform.python_version(),
        "numpy": _installed_version("numpy"),
        "torch": _installed_version("torch"),
        "torchvision": _installed_version("torchvision"),
        "platform_system": platform.system(),
        "platform_machine": platform.machine(),
        "requested_device": requested_device,
        "resolved_device": resolved_device,
    }
    domain = VQExperimentDomainAdapter(
        task_id=contract.task_id,
        policy=policy,
        contract=contract,
        contract_path=config.contract_path,
        trusted_sources=trusted_sources,
        dataset_descriptor=dataset_descriptor,
        environment_descriptor=environment_descriptor,
        command=(sys.executable, "run_training_testing.py"),
    )
    return AdaptiveExperimentRunner(
        project_dir=config.project_dir,
        task_id=contract.task_id,
        policy=policy,
        planner=planner,
        domain=domain,
        executor=executor
        or LocalSubprocessExecutionAdapter(
            timeout_seconds=config.execution_timeout_seconds
        ),
        intervention_sink=config.ledger,
    )


def _installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise EnvironmentResolutionError(
            f"required VQ distribution is unavailable: {distribution}"
        ) from exc


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_torch_device(requested: str) -> str:
    try:
        import torch
    except ImportError as exc:
        raise EnvironmentResolutionError(
            "PyTorch is unavailable for VQ environment resolution"
        ) from exc

    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise EnvironmentResolutionError("CUDA was requested but is unavailable")
    if requested == "mps" and not torch.backends.mps.is_available():
        raise EnvironmentResolutionError("MPS was requested but is unavailable")
    if requested not in {"cpu", "cuda", "mps"}:
        raise EnvironmentResolutionError(
            f"unsupported VQ device policy: {requested!r}"
        )
    return requested
