from pathlib import Path

import pytest

from research_agent.inno.experience import (
    CallableVerifier,
    CommandVerifier,
    EvaluationContract,
    ExperienceLoop,
    ExperienceQuery,
    InMemoryExperimentLedger,
    InterventionProposal,
    InterventionRecord,
    KeywordExperienceRetriever,
    KnowledgeGate,
    PrimaryMetric,
    RecallRequest,
    RunCompletion,
    TrialProvenanceRecord,
    load_evaluation_contract,
    semantic_digest,
)
from tests.test_experience.test_evaluation import observation
from tests.test_experience.test_ledger import build_records


def make_loop(ledger, events):
    evaluation_contract = EvaluationContract(
        contract_id="deterministic-score",
        task_id="task-vq",
        primary_metric=PrimaryMetric(name="score", direction="maximize"),
        baseline=0.5,
    )
    verifier = CallableVerifier(
        lambda _, observation: {
            "metrics": {"score": observation.metrics["score"]},
            "repetitions": 1,
        }
    )
    return ExperienceLoop(
        ledger=ledger,
        retriever=KeywordExperienceRetriever(ledger),
        verifier=verifier,
        knowledge_gate=KnowledgeGate(domain="vision", model_family="vq"),
        evaluation_contract=evaluation_contract,
        event_sink=lambda event, payload: events.append((event, payload)),
    )


def recall_request():
    return RecallRequest(
        query="improve the deterministic score and avoid previous failures",
        task_id="task-vq",
        domain="vision",
        dataset_id="cifar10",
        model_family="vq",
    )


def completion(
    *,
    suffix: str,
    score: float,
    iteration_number: int,
    parent_experience_ids: list[str] | None = None,
):
    hypothesis, attempt, observation, _, _, _ = build_records(suffix=suffix)
    hypothesis = hypothesis.model_copy(
        update={
            "expected_metric": "score",
            "parent_experience_ids": parent_experience_ids or [],
        }
    )
    attempt = attempt.model_copy(
        update={
            "hypothesis_id": hypothesis.hypothesis_id,
            "recall_snapshot_id": "empty"
            if not parent_experience_ids
            else "with-memory",
        }
    )
    observation = observation.model_copy(update={"metrics": {"score": score}})
    return RunCompletion(
        hypothesis=hypothesis,
        attempt=attempt,
        observation=observation,
        analysis=(
            "Avoid this configuration because it lowers the score."
            if score < 0.5
            else "Use the revised configuration because it improves the score."
        ),
        iteration_number=iteration_number,
        max_iterations=2,
    )


def test_two_iteration_loop_uses_verified_negative_experience_to_improve():
    ledger = InMemoryExperimentLedger()
    events = []
    loop = make_loop(ledger, events)

    first_recall = loop.before_run(recall_request())
    first = loop.after_run(completion(suffix="1", score=0.4, iteration_number=1))
    second_recall = loop.before_run(recall_request())
    parents = [
        source_id
        for item in second_recall.items
        for source_id in item.source_experience_ids
    ]
    second = loop.after_run(
        completion(
            suffix="2",
            score=0.8,
            iteration_number=2,
            parent_experience_ids=parents,
        )
    )

    assert first_recall.items == []
    assert first.action == "continue"
    assert first.verification is not None
    assert first.verification.outcome == "negative"
    assert len(second_recall.items) == 1
    assert second_recall.items[0].outcome == "negative"
    assert second.action == "completed"
    assert second.verification is not None
    assert second.verification.verified_metrics["score"] == 0.8
    assert second.experience is not None
    assert second.experience.hypothesis.parent_experience_ids == parents
    assert len(ledger.query(ExperienceQuery(task_id="task-vq"))) == 2
    assert "iteration_scheduled" in [event for event, _ in events]


def test_loop_restart_is_idempotent_at_durable_transitions():
    ledger = InMemoryExperimentLedger()
    loop = make_loop(ledger, [])
    run = completion(suffix="1", score=0.4, iteration_number=1)

    first = loop.after_run(run)
    repeated = loop.after_run(run)

    assert repeated == first
    assert len(ledger.query(ExperienceQuery(task_id="task-vq"))) == 1
    assert len(ledger.list_knowledge()) == 1
    assert len(ledger.list_promotion_decisions()) == 1


def test_invalid_verification_never_promotes():
    ledger = InMemoryExperimentLedger()
    evaluation_contract = EvaluationContract(
        contract_id="invalid-score",
        task_id="task-vq",
        primary_metric=PrimaryMetric(name="score", direction="maximize"),
        baseline=0.5,
    )
    loop = ExperienceLoop(
        ledger=ledger,
        retriever=KeywordExperienceRetriever(ledger),
        verifier=CallableVerifier(
            lambda *_: {"metrics": {"wrong_metric": 1.0}, "repetitions": 1}
        ),
        knowledge_gate=KnowledgeGate(domain="vision", model_family="vq"),
        evaluation_contract=evaluation_contract,
    )

    outcome = loop.after_run(
        completion(suffix="1", score=0.4, iteration_number=2)
    )

    assert outcome.action == "invalid"
    assert outcome.verification is not None
    assert outcome.verification.valid is False
    assert ledger.list_knowledge() == []
    assert ledger.list_promotion_decisions()[0].accepted is False


def test_failed_attempt_is_retained_but_never_promoted():
    ledger = InMemoryExperimentLedger()
    loop = make_loop(ledger, [])
    run = completion(suffix="1", score=0.8, iteration_number=1)
    run = run.model_copy(
        update={
            "attempt": run.attempt.model_copy(update={"status": "failed"}),
            "observation": run.observation.model_copy(
                update={"exit_code": 1, "error": {"type": "RuntimeError"}}
            ),
        }
    )

    outcome = loop.after_run(run)

    assert outcome.action == "continue"
    assert outcome.reason == "attempt_failed"
    assert outcome.experience is not None
    assert ledger.query(ExperienceQuery(task_id="task-vq")) == [
        outcome.experience
    ]
    assert ledger.list_knowledge() == []


def test_baseline_binds_trial_provenance_but_never_promotes_knowledge():
    ledger = InMemoryExperimentLedger()
    loop = make_loop(ledger, [])
    run = completion(suffix="7", score=0.8, iteration_number=1)
    run = run.model_copy(
        update={
            "attempt": run.attempt.model_copy(
                update={
                    "code_revision": "a" * 64,
                    "dataset_digest": "c" * 64,
                    "evaluation_contract_id": "deterministic-score@1",
                }
            )
        }
    )
    proposal = InterventionProposal(
        domain="vq",
        schema_id="one-layer-vq-phase-a@1",
        decision_point="vq.quantizer_optimization",
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="System-owned first-iteration baseline.",
    )
    proposal_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        proposal.model_dump(mode="json"),
    )
    resolved_config = {
        "dataset_id": "cifar10",
        "epochs": 2,
        "commitment_weight": 0.25,
    }
    config_digest = semantic_digest(
        "ai-researcher/run-config/v1",
        resolved_config,
    )
    intervention = InterventionRecord(
        intervention_id="intervention-baseline",
        run_id=run.attempt.run_id,
        iteration_id=run.attempt.iteration_id,
        task_id=run.attempt.task_id,
        hypothesis_id=run.hypothesis.hypothesis_id,
        recall_snapshot_id=run.attempt.recall_snapshot_id,
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=proposal_digest,
        resolved_config=resolved_config,
        config_digest=config_digest,
        intervention_digest=semantic_digest(
            "ai-researcher/intervention/v1",
            {"commitment_weight": 0.25},
        ),
        manipulation_status="baseline",
        violations=[],
        created_at=run.attempt.created_at,
    )
    envelope = run.observation.artifact_refs[0]
    provenance = TrialProvenanceRecord(
        provenance_id="provenance-baseline",
        attempt_id=run.attempt.attempt_id,
        observation_id=run.observation.observation_id,
        intervention_id=intervention.intervention_id,
        proposal_digest=proposal_digest,
        intervention_digest=intervention.intervention_digest,
        source_digest="a" * 64,
        config_digest=config_digest,
        environment_digest="b" * 64,
        dataset_digest="c" * 64,
        contract_digest="d" * 64,
        evaluator_digest="e" * 64,
        attempt_spec_digest="f" * 64,
        evidence_digest=semantic_digest(
            "ai-researcher/evidence-bundle/v1",
            [
                {
                    "path": Path(envelope.path).name,
                    "sha256": envelope.sha256,
                    "size_bytes": envelope.size_bytes,
                }
            ],
        ),
        execution_envelope_ref=envelope,
        created_at=run.observation.completed_at,
    )
    ledger.append_intervention(intervention)

    with pytest.raises(
        ValueError,
        match="does not match Attempt or Observation evidence",
    ):
        loop.after_run(
            run.model_copy(
                update={
                    "intervention": intervention,
                    "trial_provenance": provenance.model_copy(
                        update={"evidence_digest": "2" * 64}
                    ),
                    "manipulation_status": "baseline",
                }
            )
        )
    assert ledger.query(ExperienceQuery(task_id="task-vq")) == []

    outcome = loop.after_run(
        run.model_copy(
            update={
                "intervention": intervention,
                "trial_provenance": provenance,
                "manipulation_status": "baseline",
            }
        )
    )

    assert outcome.action == "continue"
    assert outcome.reason == "baseline_requires_intervention_attempt"
    assert outcome.experience is not None
    assert outcome.verification is not None
    assert ledger.find_trial_provenance(
        run.observation.observation_id
    ) == provenance
    assert ledger.list_knowledge() == []
    assert ledger.list_promotion_decisions()[0].reasons == [
        "baseline_has_no_intervention_effect"
    ]


def test_rejected_intervention_returns_manipulation_failure_without_fake_trial():
    ledger = InMemoryExperimentLedger()
    events = []
    loop = make_loop(ledger, events)
    proposal = InterventionProposal(
        domain="vq",
        schema_id="one-layer-vq-phase-a@1",
        decision_point="vq.quantizer_optimization",
        knob="commitment_weight",
        target=0.25,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="increase",
        guardrail_risks=[],
        rationale="The requested value does not change the previous configuration.",
    )
    intervention = InterventionRecord(
        intervention_id="intervention-rejected",
        run_id="run-rejected",
        iteration_id="iteration-2",
        task_id="task-vq",
        hypothesis_id="hypothesis-rejected",
        recall_snapshot_id="recall-rejected",
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=semantic_digest(
            "ai-researcher/proposal/v1",
            proposal.model_dump(mode="json"),
        ),
        resolved_config=None,
        config_digest=None,
        intervention_digest=None,
        manipulation_status="rejected",
        violations=["no_effect"],
        created_at=build_records(suffix="9")[1].created_at,
    )
    ledger.append_intervention(intervention)

    outcome = loop.after_intervention_rejection(
        intervention=intervention,
        reason="proposal_did_not_change_one_allowed_knob",
    )

    assert outcome.action == "manipulation_failed"
    assert ledger.list_interventions("run-rejected") == [intervention]
    assert ledger.query(ExperienceQuery(task_id="task-vq")) == []
    assert ledger.list_knowledge() == []
    assert ledger.list_promotion_decisions() == []
    assert events == [
        (
            "manipulation_failed",
            {
                "intervention_id": "intervention-rejected",
                "reason": "proposal_did_not_change_one_allowed_knob",
            },
        )
    ]


def test_adaptive_completion_missing_provenance_fails_before_ledger_writes():
    ledger = InMemoryExperimentLedger()
    loop = make_loop(ledger, [])
    snapshot_before = ledger.snapshot_id()
    run = completion(suffix="8", score=0.8, iteration_number=1)

    with pytest.raises(
        ValueError,
        match="requires Intervention and Trial Provenance",
    ):
        loop.after_run(
            run.model_copy(update={"manipulation_status": "baseline"})
        )

    assert ledger.snapshot_id() == snapshot_before
    assert ledger.query(ExperienceQuery(task_id="task-vq")) == []


class FailingRetriever:
    def recall(self, request):
        raise RuntimeError("index unavailable")


def test_retrieval_failure_degrades_to_empty_context():
    ledger = InMemoryExperimentLedger()
    loop = make_loop(ledger, [])
    loop.retriever = FailingRetriever()

    context = loop.before_run(recall_request())

    assert context.items == []
    assert context.memory_snapshot_id == ledger.snapshot_id()


def test_checked_in_deterministic_evaluator_contract_runs(tmp_path):
    contract_dir = (
        Path(__file__).resolve().parents[2]
        / "benchmark"
        / "evaluators"
        / "deterministic_score"
    )
    evaluation_contract = load_evaluation_contract(contract_dir / "contract.yaml")

    verification = CommandVerifier(contract_dir=contract_dir).verify(
        evaluation_contract,
        observation(tmp_path),
    )

    assert verification.valid is True
    assert verification.passed is True
    assert verification.verified_metrics == {"score": 0.8}
