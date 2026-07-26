from pathlib import Path

import pytest

from research_agent.inno.experience import (
    CallableVerifier,
    CommandVerifier,
    EvaluationContract,
    ExperienceLoop,
    ExperienceQuery,
    InMemoryExperimentLedger,
    KeywordExperienceRetriever,
    KnowledgeGate,
    PrimaryMetric,
    RecallRequest,
    RunCompletion,
    load_evaluation_contract,
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


class CountingVerifier:
    def __init__(self, *, fail_first: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.delegate = CallableVerifier(
            lambda _, observation: {
                "metrics": {"score": observation.metrics["score"]},
                "repetitions": 1,
            }
        )

    def verify(self, contract, observation):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise RuntimeError("simulated verifier crash")
        return self.delegate.verify(contract, observation)


class CrashAfterVerificationLedger(InMemoryExperimentLedger):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_experience = True

    def append_experience(self, experience):
        if self.fail_next_experience:
            self.fail_next_experience = False
            raise RuntimeError("simulated crash after verification")
        return super().append_experience(experience)


def make_loop_with_verifier(ledger, verifier):
    return ExperienceLoop(
        ledger=ledger,
        retriever=KeywordExperienceRetriever(ledger),
        verifier=verifier,
        knowledge_gate=KnowledgeGate(domain="vision", model_family="vq"),
        evaluation_contract=EvaluationContract(
            contract_id="deterministic-score",
            task_id="task-vq",
            primary_metric=PrimaryMetric(name="score", direction="maximize"),
            baseline=0.5,
        ),
    )


def test_restart_after_observation_retries_only_verification_and_later_stages():
    ledger = InMemoryExperimentLedger()
    verifier = CountingVerifier(fail_first=True)
    loop = make_loop_with_verifier(ledger, verifier)
    run = completion(suffix="1", score=0.8, iteration_number=1)

    with pytest.raises(RuntimeError, match="simulated verifier crash"):
        loop.after_run(run)

    assert [item.stage for item in ledger.list_transitions(run.attempt.attempt_id)] == [
        "attempt_recorded",
        "observation_recorded",
    ]

    outcome = loop.after_run(run)

    assert outcome.action == "completed"
    assert verifier.calls == 2
    assert {item.stage for item in ledger.list_transitions(run.attempt.attempt_id)} == {
        "attempt_recorded",
        "observation_recorded",
        "verification_recorded",
        "experience_recorded",
        "promotion_decided",
    }


def test_restart_after_verification_does_not_execute_evaluator_twice():
    ledger = CrashAfterVerificationLedger()
    verifier = CountingVerifier()
    loop = make_loop_with_verifier(ledger, verifier)
    run = completion(suffix="1", score=0.8, iteration_number=1)

    with pytest.raises(RuntimeError, match="simulated crash after verification"):
        loop.after_run(run)

    assert verifier.calls == 1
    assert {item.stage for item in ledger.list_transitions(run.attempt.attempt_id)} == {
        "attempt_recorded",
        "observation_recorded",
        "verification_recorded",
    }

    outcome = loop.after_run(run)

    assert outcome.action == "completed"
    assert verifier.calls == 1
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

    assert outcome.action == "invalid"
    assert outcome.reason == "attempt_failed"
    assert outcome.experience is not None
    assert ledger.query(ExperienceQuery(task_id="task-vq")) == [
        outcome.experience
    ]
    assert ledger.list_knowledge() == []


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
