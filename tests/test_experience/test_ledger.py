from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from research_agent.inno.experience import (
    ArtifactRef,
    ExperienceQuery,
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    ImmutableRecordError,
    InMemoryExperimentLedger,
    KnowledgeRecord,
    Observation,
    RecordNotFoundError,
    SQLiteExperimentLedger,
    VerificationRecord,
)


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)
DIGEST = "a" * 64


def build_records(*, suffix: str = "1", outcome: str = "positive"):
    hypothesis = Hypothesis(
        hypothesis_id=f"hypothesis-{suffix}",
        task_id="task-vq",
        statement="A transformed codebook improves utilization.",
        mechanism="The transform changes assignment geometry.",
        expected_metric="codebook_utilization",
        metric_direction="maximize",
        conditions=["CIFAR-10"],
        created_at=NOW,
    )
    attempt = ExperimentAttempt(
        attempt_id=f"attempt-{suffix}",
        run_id="run-1",
        iteration_id=f"iteration-{suffix}",
        task_id="task-vq",
        hypothesis_id=hypothesis.hypothesis_id,
        code_revision="abc123",
        dataset_id="cifar10",
        dataset_digest="dataset-sha",
        model_config_digest="model-sha",
        seed=7,
        budget={"seconds": 60, "iterations": 1},
        evaluation_contract_id="vq@1",
        recall_snapshot_id="empty",
        status="completed",
        created_at=NOW + timedelta(seconds=int(suffix)),
    )
    observation = Observation(
        observation_id=f"observation-{suffix}",
        attempt_id=attempt.attempt_id,
        exit_code=0,
        metrics={"codebook_utilization": 0.8},
        artifact_refs=[
            ArtifactRef(
                path="metrics.json",
                sha256=DIGEST,
                media_type="application/json",
                size_bytes=42,
            )
        ],
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
        environment_fingerprint="python=3.11",
    )
    verification = VerificationRecord(
        verification_id=f"verification-{suffix}",
        observation_id=observation.observation_id,
        contract_id="vq",
        contract_version="1",
        evaluator_digest=DIGEST,
        valid=True,
        passed=outcome == "positive",
        outcome=outcome,
        verified_metrics={"codebook_utilization": 0.8},
        baseline_comparison={"delta": 0.1, "direction": "maximize"},
        evidence_refs=observation.artifact_refs,
        created_at=NOW + timedelta(seconds=2),
    )
    experience = ExperienceRecord(
        experience_id=f"experience-{suffix}",
        task_id="task-vq",
        hypothesis=hypothesis,
        attempt=attempt,
        observation=observation,
        verification=verification,
        analysis="The transform improved utilization.",
        created_at=NOW + timedelta(seconds=int(suffix)),
    )
    knowledge = KnowledgeRecord(
        knowledge_id=f"knowledge-{suffix}",
        task_id="task-vq",
        domain="vision",
        dataset_id="cifar10",
        model_family="vq",
        lesson="Use the transform for this configuration.",
        conditions=["CIFAR-10"],
        outcome="positive" if outcome == "positive" else "negative",
        confidence=0.9,
        source_experience_ids=[experience.experience_id],
        promotion_policy_version="1",
        created_at=NOW + timedelta(seconds=3),
    )
    return hypothesis, attempt, observation, verification, experience, knowledge


@pytest.fixture(params=["memory", "sqlite"])
def ledger(request, tmp_path):
    if request.param == "memory":
        return InMemoryExperimentLedger()
    return SQLiteExperimentLedger(tmp_path / "experience.sqlite3")


def append_complete_record(ledger, *, suffix: str = "1", outcome: str = "positive"):
    records = build_records(suffix=suffix, outcome=outcome)
    hypothesis, attempt, observation, verification, experience, knowledge = records
    ledger.append_hypothesis(hypothesis)
    ledger.append_attempt(attempt)
    ledger.append_observation(observation)
    ledger.append_verification(verification)
    ledger.append_experience(experience)
    ledger.append_knowledge(knowledge)
    return records


def test_ledger_contract_round_trips_and_queries(ledger):
    records = append_complete_record(ledger)
    experience = records[4]

    loaded = ledger.get_experience(experience.experience_id)
    queried = ledger.query(ExperienceQuery(task_id="task-vq", valid_only=True))

    assert loaded == experience
    assert queried == [experience]
    assert ledger.list_knowledge() == [records[5]]
    assert len(ledger.snapshot_id()) == 64


def test_ledger_contract_is_idempotent_but_immutable(ledger):
    records = append_complete_record(ledger)
    hypothesis = records[0]

    ledger.append_hypothesis(hypothesis)
    changed = hypothesis.model_copy(update={"statement": "Different content."})

    with pytest.raises(ImmutableRecordError):
        ledger.append_hypothesis(changed)


def test_ledger_contract_enforces_parent_records(ledger):
    _, attempt, observation, _, _, knowledge = build_records()

    with pytest.raises(RecordNotFoundError):
        ledger.append_attempt(attempt)
    with pytest.raises(RecordNotFoundError):
        ledger.append_observation(observation)
    with pytest.raises(RecordNotFoundError):
        ledger.append_knowledge(knowledge)


def test_ledger_contract_filters_outcomes_and_orders_newest_first(ledger):
    first = append_complete_record(ledger, suffix="1", outcome="positive")
    second = append_complete_record(ledger, suffix="2", outcome="negative")

    negative = ledger.query(ExperienceQuery(outcome="negative"))
    all_records = ledger.query(ExperienceQuery())

    assert negative == [second[4]]
    assert all_records == [second[4], first[4]]


def test_sqlite_ledger_survives_process_reopen(tmp_path):
    path = tmp_path / "experience.sqlite3"
    first = SQLiteExperimentLedger(path)
    records = append_complete_record(first)
    snapshot = first.snapshot_id()

    reopened = SQLiteExperimentLedger(path)

    assert reopened.get_experience(records[4].experience_id) == records[4]
    assert reopened.list_knowledge() == [records[5]]
    assert reopened.snapshot_id() == snapshot


def test_sqlite_ledger_supports_concurrent_writers(tmp_path):
    path = tmp_path / "experience.sqlite3"
    first = SQLiteExperimentLedger(path)
    second = SQLiteExperimentLedger(path)
    hypotheses = [build_records(suffix=str(index))[0] for index in range(1, 9)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                first.append_hypothesis if index % 2 else second.append_hypothesis,
                hypothesis,
            )
            for index, hypothesis in enumerate(hypotheses)
        ]
        for future in futures:
            future.result()

    with first._connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM hypotheses").fetchone()[0]
    assert count == len(hypotheses)
