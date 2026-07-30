from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from research_agent.inno.experience.evaluation import (
    AdaptiveExperimentPolicy,
    EvaluationContract,
    InterventionKnob,
    PrimaryMetric,
)
from research_agent.inno.experience.intervention import (
    InterventionProposal,
    InterventionRecord,
    semantic_digest,
)
from research_agent.inno.experience.ledger import InMemoryExperimentLedger
from research_agent.inno.experience.models import Hypothesis
from research_agent.runtime.adaptive_experiment import (
    AdaptiveExperimentResult,
    AdaptiveExperimentRequest,
    AdaptiveExperimentRunner,
    AttemptSpecConflict,
    DomainExecutionPlan,
    EvidenceCollision,
    ExperimentExecutionError,
    InMemoryExecutionAdapter,
    InterventionPolicyViolation,
    InterventionProposalError,
    LocalSubprocessExecutionAdapter,
    PreviousAttemptFeedback,
    ProvenanceBindingError,
    TrialPreflight,
)
from research_agent.runtime.domain_adapters.synthetic import (
    SyntheticResponseSurfaceAdapter,
)
from research_agent.runtime.domain_adapters.vq import VQExperimentDomainAdapter
from research_agent.runtime.trial_provenance import file_set_digest, raw_sha256


class _PlannerMustNotRun:
    async def propose(self, context):
        raise AssertionError("the first Experiment Attempt must not invoke the planner")


class _InterventionSink:
    def __init__(self, records=()) -> None:
        self.records = list(records)

    def append_intervention(self, record) -> None:
        self.records.append(record)

    def get_intervention(self, intervention_id):
        for record in self.records:
            if record.intervention_id == intervention_id:
                return record
        raise KeyError(intervention_id)

    def list_interventions(self, run_id):
        return [
            record for record in self.records if record.run_id == run_id
        ]


class _FixedPlanner:
    def __init__(self, proposal: InterventionProposal) -> None:
        self.proposal = proposal
        self.contexts = []

    async def propose(self, context):
        self.contexts.append(context)
        return self.proposal


class _CountingExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.delegate = InMemoryExecutionAdapter()

    def execute(self, plan):
        self.calls += 1
        return self.delegate.execute(plan)


class _SpecTamperingExecutor:
    def execute(self, plan):
        plan.spec_path.chmod(0o644)
        plan.spec_path.write_text('{"tampered":true}', encoding="utf-8")
        return InMemoryExecutionAdapter().execute(plan)


def _subprocess_plan(
    tmp_path: Path,
    *,
    command: tuple[str, ...],
    environment: dict[str, str] | None = None,
) -> DomainExecutionPlan:
    evidence_dir = tmp_path / "raw-evidence"
    evidence_dir.mkdir()
    config = {"seed": 401}
    return DomainExecutionPlan(
        preflight=TrialPreflight(
            attempt_key="run-1:iteration-001",
            proposal_digest="1" * 64,
            intervention_digest="2" * 64,
            config_digest=semantic_digest(
                "ai-researcher/run-config/v1",
                config,
            ),
            source_digest="3" * 64,
            dataset_digest="4" * 64,
            environment_digest="5" * 64,
            contract_digest="6" * 64,
            evaluator_digest="7" * 64,
            attempt_spec_digest="8" * 64,
            effective_config=config,
            manipulation_status="baseline",
        ),
        spec_path=evidence_dir / "attempt_spec.json",
        command=command,
        cwd=tmp_path,
        evidence_dir=evidence_dir,
        environment=environment or {},
        required_artifacts=("run.log",),
    )


def _policy(*, no_op_policy: str = "reject_before_execution"):
    return AdaptiveExperimentPolicy(
        policy_id="synthetic-phase-a",
        version="1",
        decision_point="synthetic.response_surface",
        no_op_policy=no_op_policy,
        max_changes_per_attempt=1,
        defaults={"gain": 1.0, "bias": 0.0},
        knobs={
            "gain": InterventionKnob(
                value_type="number",
                allowed_values=[0.5, 1.0, 2.0],
            ),
            "bias": InterventionKnob(
                value_type="number",
                allowed_values=[-1.0, 0.0, 1.0],
            ),
        },
        fixed_config={"dataset_id": "synthetic", "samples": 32},
        source_files=["synthetic.py"],
        expected_source_digest="0" * 64,
    )


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        hypothesis_id="hypothesis-1",
        task_id="synthetic:task1",
        statement="Increasing gain improves the response.",
        mechanism="The response surface is monotonic in gain.",
        expected_metric="score",
        metric_direction="maximize",
    )


def _persisted_baseline(
    policy: AdaptiveExperimentPolicy,
    previous: PreviousAttemptFeedback,
    *,
    run_id: str = "run-1",
    iteration_number: int = 1,
) -> InterventionRecord:
    proposal = InterventionProposal(
        domain="synthetic",
        schema_id="synthetic.response-surface/v1",
        decision_point=policy.decision_point,
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="Persisted baseline fixture.",
    )
    return InterventionRecord(
        intervention_id=previous.intervention_id,
        run_id=run_id,
        iteration_id=f"iteration-{iteration_number:03d}",
        task_id="synthetic:task1",
        hypothesis_id=_hypothesis().hypothesis_id,
        recall_snapshot_id="off",
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=semantic_digest(
            "ai-researcher/proposal/v1",
            proposal.model_dump(mode="json"),
        ),
        resolved_config=previous.effective_config,
        config_digest=previous.config_digest,
        intervention_digest=semantic_digest(
            "ai-researcher/intervention/v1",
            {
                name: previous.effective_config[name]
                for name in policy.knobs
            },
        ),
        manipulation_status="baseline",
        violations=[],
        created_at=_hypothesis().created_at,
    )


def test_first_attempt_executes_catalog_baseline_without_planner(tmp_path: Path) -> None:
    policy = _policy()
    sink = _InterventionSink()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=sink,
    )

    result = asyncio.run(
        runner.run(
            AdaptiveExperimentRequest(
                run_id="run-1",
                iteration_number=1,
                hypothesis=_hypothesis(),
                seed=401,
                attempt_cache_path=(
                    tmp_path / "attempts" / "iteration-001"
                ),
                evidence_dir=tmp_path / "attempts" / "iteration-001" / "raw-evidence",
                recall_context=None,
                previous=None,
            )
        )
    )

    assert result.status == "executed"
    assert result.preflight.manipulation_status == "baseline"
    assert result.preflight.effective_config["gain"] == 1.0
    assert result.receipt is not None
    assert result.receipt.actual_config == result.preflight.effective_config
    assert len(sink.records) == 1
    assert sink.records[0] == result.intervention
    assert sink.records[0].manipulation_status == "baseline"


def test_result_rejects_preflight_digests_that_differ_from_intervention(
    tmp_path: Path,
) -> None:
    policy = _policy()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=_InterventionSink(),
    )
    result = asyncio.run(
        runner.run(
            AdaptiveExperimentRequest(
                run_id="run-1",
                iteration_number=1,
                hypothesis=_hypothesis(),
                seed=401,
                attempt_cache_path=(
                    tmp_path / "attempts" / "iteration-001"
                ),
                evidence_dir=(
                    tmp_path / "attempts" / "iteration-001" / "raw-evidence"
                ),
                recall_context=None,
                previous=None,
            )
        )
    )
    assert result.receipt is not None
    forged_preflight = result.preflight.model_copy(
        update={"proposal_digest": "f" * 64}
    )
    forged_receipt = result.receipt.model_copy(
        update={"proposal_digest": "f" * 64}
    )

    with pytest.raises(
        ValueError,
        match="Intervention and preflight digests differ",
    ):
        AdaptiveExperimentResult(
            status="executed",
            intervention=result.intervention,
            preflight=forged_preflight,
            receipt=forged_receipt,
        )


def test_request_rejects_seed_outside_frozen_spec_range() -> None:
    with pytest.raises(ValueError, match="less than"):
        AdaptiveExperimentRequest(
            run_id="run-1",
            iteration_number=1,
            hypothesis=_hypothesis(),
            seed=2**63,
            attempt_cache_path=Path("attempts/iteration-001"),
            evidence_dir=Path("attempts/iteration-001/raw-evidence"),
            recall_context=None,
            previous=None,
        )


def test_runner_rejects_evidence_directory_outside_iteration_layout(
    tmp_path: Path,
) -> None:
    policy = _policy()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=_InterventionSink(),
    )
    invalid_evidence_dir = tmp_path / "unbound" / "raw-evidence"

    with pytest.raises(
        InterventionPolicyViolation,
        match="iteration-specific attempt cache",
    ):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=1,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=tmp_path / "unbound",
                    evidence_dir=invalid_evidence_dir,
                    recall_context=None,
                    previous=None,
                )
            )
        )

    assert not invalid_evidence_dir.exists()


def test_runner_rejects_evidence_directory_outside_authorized_attempt_cache(
    tmp_path: Path,
) -> None:
    policy = _policy()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=_InterventionSink(),
    )
    authorized_cache = (
        tmp_path / "authorized" / "attempts" / "iteration-001"
    )
    unbound_evidence_dir = (
        tmp_path
        / "unbound"
        / "attempts"
        / "iteration-001"
        / "raw-evidence"
    )

    with pytest.raises(
        InterventionPolicyViolation,
        match="authorized attempt cache",
    ):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=1,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=authorized_cache,
                    evidence_dir=unbound_evidence_dir,
                    recall_context=None,
                    previous=None,
                )
            )
        )

    assert not unbound_evidence_dir.exists()


def test_runner_rejects_symlinked_attempt_cache(tmp_path: Path) -> None:
    policy = _policy()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=_InterventionSink(),
    )
    real_cache = tmp_path / "real" / "iteration-001"
    real_cache.mkdir(parents=True)
    linked_attempts = tmp_path / "linked" / "attempts"
    linked_attempts.mkdir(parents=True)
    linked_cache = linked_attempts / "iteration-001"
    linked_cache.symlink_to(real_cache, target_is_directory=True)

    with pytest.raises(
        InterventionPolicyViolation,
        match="authorized attempt cache",
    ):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=1,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=linked_cache,
                    evidence_dir=linked_cache / "raw-evidence",
                    recall_context=None,
                    previous=None,
                )
            )
        )

    assert not (real_cache / "raw-evidence").exists()


def test_later_attempt_executes_one_catalog_change_from_verified_feedback(
    tmp_path: Path,
) -> None:
    policy = _policy()
    previous_config = {
        **policy.fixed_config,
        **policy.defaults,
        "seed": 401,
        "device": "cpu",
    }
    previous = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            previous_config,
        ),
        effective_config=previous_config,
        verified_metrics={"score": 2.0},
        outcome="neutral",
        guardrail_violations=[],
    )
    planner = _FixedPlanner(
        InterventionProposal(
            domain="synthetic",
            schema_id="synthetic.response-surface/v1",
            decision_point=policy.decision_point,
            knob="gain",
            target=2.0,
            cited_knowledge_ids=[],
            expected_primary_metric_direction="increase",
            guardrail_risks=[],
            rationale="Exercise the higher allowed gain.",
        )
    )
    sink = _InterventionSink([_persisted_baseline(policy, previous)])
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=planner,
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=sink,
    )

    result = asyncio.run(
        runner.run(
            AdaptiveExperimentRequest(
                run_id="run-1",
                iteration_number=2,
                hypothesis=_hypothesis(),
                seed=401,
                attempt_cache_path=(
                    tmp_path / "attempts" / "iteration-002"
                ),
                evidence_dir=tmp_path / "attempts" / "iteration-002" / "raw-evidence",
                recall_context=None,
                previous=previous,
            )
        )
    )

    assert result.status == "executed"
    assert result.preflight.manipulation_status == "changed"
    assert result.preflight.effective_config["gain"] == 2.0
    assert result.intervention.previous_intervention_id == "intervention-1"
    assert len(planner.contexts) == 1
    assert planner.contexts[0].previous.verified_metrics == {"score": 2.0}


def test_pilot_no_effect_is_recorded_but_rejected_before_execution(
    tmp_path: Path,
) -> None:
    policy = _policy(no_op_policy="reject_before_execution")
    previous_config = {
        **policy.fixed_config,
        **policy.defaults,
        "seed": 401,
        "device": "cpu",
    }
    previous = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            previous_config,
        ),
        effective_config=previous_config,
        verified_metrics={"score": 2.0},
        outcome="neutral",
        guardrail_violations=[],
    )
    planner = _FixedPlanner(
        InterventionProposal(
            domain="synthetic",
            schema_id="synthetic.response-surface/v1",
            decision_point=policy.decision_point,
            knob="gain",
            target=1.0,
            cited_knowledge_ids=[],
            expected_primary_metric_direction="increase",
            guardrail_risks=[],
            rationale="This deliberately proposes the current value.",
        )
    )
    sink = _InterventionSink([_persisted_baseline(policy, previous)])
    executor = _CountingExecutor()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=planner,
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=executor,
        intervention_sink=sink,
    )

    result = asyncio.run(
        runner.run(
            AdaptiveExperimentRequest(
                run_id="run-1",
                iteration_number=2,
                hypothesis=_hypothesis(),
                seed=401,
                attempt_cache_path=(
                    tmp_path / "attempts" / "iteration-002"
                ),
                evidence_dir=tmp_path / "attempts" / "iteration-002" / "raw-evidence",
                recall_context=None,
                previous=previous,
            )
        )
    )

    assert result.status == "rejected_no_effect"
    assert result.preflight.manipulation_status == "no_effect"
    assert result.intervention.manipulation_status == "no_effect"
    assert result.receipt is None
    assert executor.calls == 0
    assert len(sink.records) == 2


def test_confirmatory_no_effect_executes_and_is_explicitly_marked(
    tmp_path: Path,
) -> None:
    policy = _policy(no_op_policy="execute_and_mark")
    previous_config = {
        **policy.fixed_config,
        **policy.defaults,
        "seed": 401,
        "device": "cpu",
    }
    previous = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            previous_config,
        ),
        effective_config=previous_config,
        verified_metrics={"score": 2.0},
        outcome="neutral",
        guardrail_violations=[],
    )
    planner = _FixedPlanner(
        InterventionProposal(
            domain="synthetic",
            schema_id="synthetic.response-surface/v1",
            decision_point=policy.decision_point,
            knob="gain",
            target=1.0,
            cited_knowledge_ids=[],
            expected_primary_metric_direction="unchanged",
            guardrail_risks=[],
            rationale="Preserve the assignment for an intention-to-treat trial.",
        )
    )
    sink = _InterventionSink([_persisted_baseline(policy, previous)])
    executor = _CountingExecutor()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=planner,
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=executor,
        intervention_sink=sink,
    )

    result = asyncio.run(
        runner.run(
            AdaptiveExperimentRequest(
                run_id="run-1",
                iteration_number=2,
                hypothesis=_hypothesis(),
                seed=401,
                attempt_cache_path=(
                    tmp_path / "attempts" / "iteration-002"
                ),
                evidence_dir=tmp_path / "attempts" / "iteration-002" / "raw-evidence",
                recall_context=None,
                previous=previous,
            )
        )
    )

    assert result.status == "executed_no_effect"
    assert result.receipt is not None
    assert result.receipt.actual_config == previous_config
    assert executor.calls == 1


def test_planner_cannot_cite_knowledge_outside_the_recall_context(
    tmp_path: Path,
) -> None:
    policy = _policy()
    previous_config = {
        **policy.fixed_config,
        **policy.defaults,
        "seed": 401,
        "device": "cpu",
    }
    previous = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            previous_config,
        ),
        effective_config=previous_config,
        verified_metrics={"score": 2.0},
        outcome="neutral",
        guardrail_violations=[],
    )
    planner = _FixedPlanner(
        InterventionProposal(
            domain="synthetic",
            schema_id="synthetic.response-surface/v1",
            decision_point=policy.decision_point,
            knob="gain",
            target=2.0,
            cited_knowledge_ids=["knowledge-not-recalled"],
            expected_primary_metric_direction="increase",
            guardrail_risks=[],
            rationale="This citation was not supplied to the planner.",
        )
    )
    sink = _InterventionSink([_persisted_baseline(policy, previous)])
    executor = _CountingExecutor()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=planner,
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=executor,
        intervention_sink=sink,
    )

    with pytest.raises(
        InterventionProposalError,
        match="not present in the Recall Context",
    ):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=2,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=(
                        tmp_path / "attempts" / "iteration-002"
                    ),
                    evidence_dir=(
                        tmp_path / "attempts" / "iteration-002" / "raw-evidence"
                    ),
                    recall_context=None,
                    previous=previous,
                )
            )
        )

    assert len(sink.records) == 1
    assert executor.calls == 0


@pytest.mark.parametrize(
    ("persisted_run_id", "persisted_iteration", "request_iteration"),
    [
        ("other-run", 1, 2),
        ("run-1", 1, 3),
    ],
)
def test_previous_feedback_must_bind_to_same_run_and_adjacent_iteration(
    tmp_path: Path,
    persisted_run_id: str,
    persisted_iteration: int,
    request_iteration: int,
) -> None:
    policy = _policy()
    previous_config = {
        **policy.fixed_config,
        **policy.defaults,
        "seed": 401,
        "device": "cpu",
    }
    previous = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            previous_config,
        ),
        effective_config=previous_config,
        verified_metrics={"score": 2.0},
        outcome="neutral",
        guardrail_violations=[],
    )
    planner = _FixedPlanner(
        InterventionProposal(
            domain="synthetic",
            schema_id="synthetic.response-surface/v1",
            decision_point=policy.decision_point,
            knob="gain",
            target=2.0,
            cited_knowledge_ids=[],
            expected_primary_metric_direction="increase",
            guardrail_risks=[],
            rationale="Exercise one valid catalog change.",
        )
    )
    sink = _InterventionSink(
        [
            _persisted_baseline(
                policy,
                previous,
                run_id=persisted_run_id,
                iteration_number=persisted_iteration,
            )
        ]
    )
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=planner,
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=sink,
    )
    evidence_dir = (
        tmp_path
        / "attempts"
        / f"iteration-{request_iteration:03d}"
        / "raw-evidence"
    )

    with pytest.raises(
        ProvenanceBindingError,
        match="previous feedback",
    ):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=request_iteration,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=evidence_dir.parent,
                    evidence_dir=evidence_dir,
                    recall_context=None,
                    previous=previous,
                )
            )
        )

    assert planner.contexts == []
    assert not evidence_dir.exists()


def test_completed_attempt_retry_returns_same_receipt_without_reexecution(
    tmp_path: Path,
) -> None:
    policy = _policy()
    ledger = InMemoryExperimentLedger()
    executor = _CountingExecutor()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=executor,
        intervention_sink=ledger,
    )
    request = AdaptiveExperimentRequest(
        run_id="run-1",
        iteration_number=1,
        hypothesis=_hypothesis(),
        seed=401,
        attempt_cache_path=tmp_path / "attempts" / "iteration-001",
        evidence_dir=tmp_path / "attempts" / "iteration-001" / "raw-evidence",
        recall_context=None,
        previous=None,
    )

    first = asyncio.run(runner.run(request))
    retried = asyncio.run(runner.run(request))

    assert retried == first
    assert executor.calls == 1
    assert ledger.list_interventions("run-1") == [first.intervention]


def test_baseline_preflight_persists_intervention_without_execution(
    tmp_path: Path,
) -> None:
    policy = _policy()
    ledger = InMemoryExperimentLedger()
    executor = _CountingExecutor()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=executor,
        intervention_sink=ledger,
    )
    request = AdaptiveExperimentRequest(
        run_id="dry-run-1",
        iteration_number=1,
        hypothesis=_hypothesis(),
        seed=401,
        attempt_cache_path=tmp_path / "attempts" / "iteration-001",
        evidence_dir=tmp_path / "attempts" / "iteration-001" / "raw-evidence",
        recall_context=None,
        previous=None,
    )

    prepared = asyncio.run(runner.prepare_baseline(request))

    assert prepared.preflight.manipulation_status == "baseline"
    assert prepared.attempt_spec_ref.path.endswith("attempt_spec.json")
    assert ledger.list_interventions("dry-run-1") == [prepared.intervention]
    assert executor.calls == 0
    assert sorted(path.name for path in request.evidence_dir.iterdir()) == [
        "attempt_spec.json"
    ]


def test_execution_fails_closed_if_spec_changes_after_preflight(
    tmp_path: Path,
) -> None:
    policy = _policy()
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=_SpecTamperingExecutor(),
        intervention_sink=_InterventionSink(),
    )

    with pytest.raises(AttemptSpecConflict, match="changed after preflight"):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=1,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=(
                        tmp_path / "attempts" / "iteration-001"
                    ),
                    evidence_dir=(
                        tmp_path / "attempts" / "iteration-001" / "raw-evidence"
                    ),
                    recall_context=None,
                    previous=None,
                )
            )
        )


@pytest.mark.parametrize(
    "environment_name",
    [
        "ai_ping_api_key",
        "database_PASSWORD",
        "Authorization",
    ],
)
def test_local_executor_redacts_secret_environment_values_from_logs(
    tmp_path: Path,
    environment_name: str,
) -> None:
    evidence_dir = tmp_path / "raw-evidence"
    evidence_dir.mkdir()
    config = {"seed": 401}
    preflight = TrialPreflight(
        attempt_key="run-1:iteration-001",
        proposal_digest="1" * 64,
        intervention_digest="2" * 64,
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            config,
        ),
        source_digest="3" * 64,
        dataset_digest="4" * 64,
        environment_digest="5" * 64,
        contract_digest="6" * 64,
        evaluator_digest="7" * 64,
        attempt_spec_digest="8" * 64,
        effective_config=config,
        manipulation_status="baseline",
    )
    secret = "must-not-enter-an-artifact"
    plan = DomainExecutionPlan(
        preflight=preflight,
        spec_path=evidence_dir / "attempt_spec.json",
        command=(
            sys.executable,
            "-c",
            (
                "import os, sys; "
                f"print(os.environ[{environment_name!r}]); "
                "print('stderr diagnostic', file=sys.stderr); "
                "print('completed')"
            ),
        ),
        cwd=tmp_path,
        evidence_dir=evidence_dir,
        environment={environment_name: secret},
        required_artifacts=("run.log",),
    )

    LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    log = (evidence_dir / "run.log").read_text(encoding="utf-8")
    assert secret not in log
    assert f"<redacted:{environment_name}>" in log
    assert "stderr diagnostic" in log
    assert "completed" in log


def test_local_executor_atomically_redacts_logs_written_by_successful_process(
    tmp_path: Path,
) -> None:
    secret = "must-not-survive-in-process-authored-logs"
    evidence_dir = tmp_path / "raw-evidence"
    script = (
        "from pathlib import Path; "
        "import os; "
        f"evidence = Path({str(evidence_dir)!r}); "
        "content = 'credential=' + os.environ['SECRET_KEY']; "
        "(evidence / 'run.log').write_text(content, encoding='utf-8'); "
        "(evidence / 'executor.log').write_text(content, encoding='utf-8'); "
        "print('completed')"
    )
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", script),
        environment={"SECRET_KEY": secret},
    )

    receipt = LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    assert receipt.exit_code == 0
    for logical_name in ("run.log", "executor.log"):
        log = (evidence_dir / logical_name).read_text(encoding="utf-8")
        assert secret not in log
        assert "<redacted:SECRET_KEY>" in log


def test_local_executor_rejects_process_authored_log_symlink(
    tmp_path: Path,
) -> None:
    outside_log = tmp_path / "outside.log"
    outside_log.write_text("must remain unchanged", encoding="utf-8")
    evidence_dir = tmp_path / "raw-evidence"
    script = (
        "from pathlib import Path; "
        f"evidence = Path({str(evidence_dir)!r}); "
        f"(evidence / 'run.log').symlink_to({str(outside_log)!r})"
    )
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", script),
    )

    with pytest.raises(EvidenceCollision, match="regular non-symlink"):
        LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    assert outside_log.read_text(encoding="utf-8") == "must remain unchanged"


def test_local_executor_atomically_creates_missing_run_log(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import research_agent.runtime.adaptive_experiment as adaptive_module

    outside_log = tmp_path / "outside.log"
    outside_log.write_text("must remain unchanged", encoding="utf-8")
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", "print('completed')"),
    )
    real_redactor = adaptive_module._redact_existing_evidence_log

    def inject_symlink_after_missing_check(
        evidence_dir,
        logical_name,
        environment,
        **kwargs,
    ):
        result = real_redactor(
            evidence_dir,
            logical_name,
            environment,
            **kwargs,
        )
        if (
            logical_name == "run.log"
            and kwargs.get("content_if_missing") is None
            and not result
        ):
            (evidence_dir / logical_name).symlink_to(outside_log)
        return result

    monkeypatch.setattr(
        adaptive_module,
        "_redact_existing_evidence_log",
        inject_symlink_after_missing_check,
    )

    receipt = LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    assert receipt.exit_code == 0
    assert outside_log.read_text(encoding="utf-8") == "must remain unchanged"
    run_log = plan.evidence_dir / "run.log"
    assert not run_log.is_symlink()
    assert "completed" in run_log.read_text(encoding="utf-8")


def test_local_executor_preserves_nonzero_status_and_captures_both_streams(
    tmp_path: Path,
) -> None:
    plan = _subprocess_plan(
        tmp_path,
        command=(
            sys.executable,
            "-c",
            (
                "import sys; "
                "print('stdout before failure'); "
                "print('stderr before failure', file=sys.stderr); "
                "raise SystemExit(7)"
            ),
        ),
    )

    with pytest.raises(
        ExperimentExecutionError,
        match="exited with status 7",
    ):
        LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    failure_log = (plan.evidence_dir / "executor.log").read_text(encoding="utf-8")
    assert "stdout before failure" in failure_log
    assert "stderr before failure" in failure_log
    assert not (plan.evidence_dir / "run.log").exists()


def test_local_executor_nonzero_rejects_executor_log_symlink(
    tmp_path: Path,
) -> None:
    outside_log = tmp_path / "outside-executor.log"
    outside_log.write_text("must remain unchanged", encoding="utf-8")
    evidence_dir = tmp_path / "raw-evidence"
    script = (
        "from pathlib import Path; "
        f"evidence = Path({str(evidence_dir)!r}); "
        f"(evidence / 'executor.log').symlink_to({str(outside_log)!r}); "
        "raise SystemExit(7)"
    )
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", script),
    )

    with pytest.raises(EvidenceCollision, match="regular non-symlink"):
        LocalSubprocessExecutionAdapter(timeout_seconds=10).execute(plan)

    assert outside_log.read_text(encoding="utf-8") == "must remain unchanged"


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_local_executor_timeout_terminates_grandchild_process_group(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "grandchild-survived"
    pid_path = tmp_path / "grandchild.pid"
    grandchild_script = (
        "from pathlib import Path; "
        "import time; "
        "time.sleep(0.8); "
        f"Path({str(marker_path)!r}).write_text('survived', encoding='utf-8'); "
        "time.sleep(0.2)"
    )
    parent_script = (
        "from pathlib import Path; "
        "import subprocess, sys, time; "
        f"child = subprocess.Popen([sys.executable, '-c', {grandchild_script!r}]); "
        f"Path({str(pid_path)!r}).write_text(str(child.pid), encoding='utf-8'); "
        "print('stdout before timeout', flush=True); "
        "print('stderr before timeout', file=sys.stderr, flush=True); "
        "time.sleep(30)"
    )
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", parent_script),
    )

    with pytest.raises(ExperimentExecutionError, match="exceeded 0.3 seconds"):
        LocalSubprocessExecutionAdapter(timeout_seconds=0.3).execute(plan)

    assert pid_path.exists()
    time.sleep(0.9)
    assert not marker_path.exists()
    failure_log = (plan.evidence_dir / "executor.log").read_text(encoding="utf-8")
    assert "stdout before timeout" in failure_log
    assert "stderr before timeout" in failure_log
    grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
    status = subprocess.run(
        ("ps", "-o", "stat=", "-p", str(grandchild_pid)),
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not status or status.startswith("Z")


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX process groups")
def test_local_executor_timeout_kills_grandchild_that_ignores_term(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "term-ignoring-grandchild-survived"
    ready_path = tmp_path / "term-handler-ready"
    pid_path = tmp_path / "term-ignoring-grandchild.pid"
    grandchild_script = (
        "from pathlib import Path; "
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"Path({str(ready_path)!r}).write_text('ready', encoding='utf-8'); "
        "time.sleep(0.8); "
        f"Path({str(marker_path)!r}).write_text('survived', encoding='utf-8'); "
        "time.sleep(0.2)"
    )
    parent_script = (
        "from pathlib import Path; "
        "import subprocess, sys, time; "
        f"child = subprocess.Popen([sys.executable, '-c', {grandchild_script!r}]); "
        f"Path({str(pid_path)!r}).write_text(str(child.pid), encoding='utf-8'); "
        f"ready = Path({str(ready_path)!r}); "
        "deadline = time.monotonic() + 10; "
        "exec(\"while not ready.exists() and time.monotonic() < deadline:\\n"
        "    time.sleep(0.01)\"); "
        "time.sleep(30)"
    )
    plan = _subprocess_plan(
        tmp_path,
        command=(sys.executable, "-c", parent_script),
    )

    with pytest.raises(ExperimentExecutionError, match="exceeded 0.5 seconds"):
        LocalSubprocessExecutionAdapter(timeout_seconds=0.5).execute(plan)

    assert ready_path.exists()
    time.sleep(0.9)
    assert not marker_path.exists()
    grandchild_pid = int(pid_path.read_text(encoding="utf-8"))
    status = subprocess.run(
        ("ps", "-o", "stat=", "-p", str(grandchild_pid)),
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not status or status.startswith("Z")


def test_retry_rejects_an_execution_envelope_with_different_bytes(
    tmp_path: Path,
) -> None:
    policy = _policy()
    evidence_dir = tmp_path / "attempts" / "iteration-001" / "raw-evidence"
    evidence_dir.mkdir(parents=True)
    (evidence_dir / "attempt_spec.json").write_text(
        '{"attempt_key":"another-attempt"}',
        encoding="utf-8",
    )
    runner = AdaptiveExperimentRunner(
        project_dir=tmp_path / "project",
        task_id="synthetic:task1",
        policy=policy,
        planner=_PlannerMustNotRun(),
        domain=SyntheticResponseSurfaceAdapter(
            task_id="synthetic:task1",
            policy=policy,
        ),
        executor=InMemoryExecutionAdapter(),
        intervention_sink=_InterventionSink(),
    )

    with pytest.raises(AttemptSpecConflict, match="execution envelope"):
        asyncio.run(
            runner.run(
                AdaptiveExperimentRequest(
                    run_id="run-1",
                    iteration_number=1,
                    hypothesis=_hypothesis(),
                    seed=401,
                    attempt_cache_path=evidence_dir.parent,
                    evidence_dir=evidence_dir,
                    recall_context=None,
                    previous=None,
                )
            )
        )


def test_vq_domain_preflight_restores_and_attests_only_trusted_sources(
    tmp_path: Path,
) -> None:
    template_root = tmp_path / "templates"
    template_root.mkdir()
    trusted_sources = {
        "protocol.py": template_root / "protocol.py",
        "run_training_testing.py": template_root / "run_training_testing.py",
        "attempt_spec.py": template_root / "attempt_spec.py",
    }
    for logical_name, path in trusted_sources.items():
        path.write_text(f"# trusted {logical_name}\n", encoding="utf-8")
    source_digest = file_set_digest(
        "ai-researcher/source-set/v1",
        trusted_sources,
    )
    policy = AdaptiveExperimentPolicy(
        policy_id="one-layer-vq-phase-a",
        version="1",
        decision_point="vq.quantizer_optimization",
        no_op_policy="reject_before_execution",
        max_changes_per_attempt=1,
        defaults={
            "projection_lr_multiplier": 1.0,
            "commitment_weight": 0.25,
        },
        knobs={
            "projection_lr_multiplier": InterventionKnob(
                value_type="number",
                allowed_values=[0.5, 1.0, 2.0],
            ),
            "commitment_weight": InterventionKnob(
                value_type="number",
                allowed_values=[0.1, 0.25, 0.5],
            ),
        },
        fixed_config={
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
        },
        source_files=list(trusted_sources),
        expected_source_digest=source_digest,
    )
    evaluator_path = tmp_path / "evaluate_v3.py"
    evaluator_path.write_text("# evaluator\n", encoding="utf-8")
    contract_path = tmp_path / "contract.yaml"
    contract_path.write_text("contract bytes are independently attested\n")
    contract = EvaluationContract(
        schema_version=2,
        contract_id="one-layer-vq-cifar10-adaptive",
        version="3-phase-a",
        task_id="one_layer_vq:task1",
        entrypoint='python evaluate_v3.py "{attempt_dir}"',
        required_artifacts=[
            "attempt_spec.json",
            "evaluation_manifest.json",
            "evaluation_arrays.npz",
            "run.log",
        ],
        evaluator_files=["evaluate_v3.py"],
        primary_metric=PrimaryMetric(
            name="codebook_utilization",
            direction="maximize",
        ),
        baseline=0.95,
        adaptive_experiment=policy,
    )
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    for logical_name in trusted_sources:
        (project_dir / logical_name).write_text("# agent mutation\n")
    adapter = VQExperimentDomainAdapter(
        task_id=contract.task_id,
        policy=policy,
        contract=contract,
        contract_path=contract_path,
        trusted_sources=trusted_sources,
        dataset_descriptor={
            "dataset_id": "cifar10",
            "archive_sha256": "a" * 64,
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
            statement="Use the frozen VQ baseline.",
            mechanism="Baseline establishes the comparison.",
            expected_metric="codebook_utilization",
            metric_direction="maximize",
        ),
        seed=401,
        attempt_cache_path=tmp_path / "attempts" / "iteration-001",
        evidence_dir=tmp_path / "attempts" / "iteration-001" / "raw-evidence",
        recall_context=None,
        previous=None,
    )

    resolved = adapter.baseline(policy=policy, seed=request.seed)
    plan = adapter.prepare(
        resolved,
        request=request,
        project_dir=project_dir,
        evidence_dir=request.evidence_dir,
    )

    assert plan.preflight.source_digest == source_digest
    assert plan.preflight.effective_config["resolved_device"] == "cpu"
    assert plan.preflight.effective_config["train_split"] == "train"
    spec = json.loads(plan.spec_path.read_text(encoding="utf-8"))
    assert spec["descriptors"]["dataset"]["train_selector"]["seed"] == 401
    assert spec["descriptors"]["environment"]["requested_device"] == "auto"
    assert plan.preflight.dataset_digest == semantic_digest(
        "ai-researcher/dataset-plan/v1",
        spec["descriptors"]["dataset"],
    )
    assert plan.preflight.environment_digest == semantic_digest(
        "ai-researcher/environment/v1",
        spec["descriptors"]["environment"],
    )
    assert plan.environment["AI_RESEARCHER_ATTEMPT_SPEC"] == str(
        plan.spec_path.resolve()
    )
    assert plan.environment["AI_RESEARCHER_ATTEMPT_SPEC_SHA256"] == raw_sha256(
        plan.spec_path.read_bytes()
    )
    for logical_name, template in trusted_sources.items():
        assert (project_dir / logical_name).read_bytes() == template.read_bytes()
