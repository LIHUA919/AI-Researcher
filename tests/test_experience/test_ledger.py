from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from research_agent.inno.experience import (
    ArtifactRef,
    ExperienceQuery,
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    ImmutableRecordError,
    InMemoryExperimentLedger,
    InterventionProposal,
    InterventionRecord,
    KnowledgeRecord,
    Observation,
    RecordNotFoundError,
    SQLiteExperimentLedger,
    TrialProvenanceRecord,
    VerificationRecord,
    semantic_digest,
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
        baseline_comparison={
            "metric": "codebook_utilization",
            "baseline": 0.7,
            "value": 0.8,
            "delta": 0.1,
            "direction": "maximize",
        },
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


def build_sidecars(records, *, suffix: str = "1"):
    hypothesis, attempt, observation, _, _, _ = records
    proposal = InterventionProposal(
        domain="vq",
        schema_id="vq.intervention@1",
        decision_point="optimizer",
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="Establish the fixed baseline.",
    )
    resolved_config = {
        "learning_rate": 0.0003,
        "projection_lr_multiplier": 1.0,
        "seed": attempt.seed,
    }
    proposal_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        proposal.model_dump(mode="json"),
    )
    config_digest = semantic_digest(
        "ai-researcher/run-config/v1",
        resolved_config,
    )
    intervention = InterventionRecord(
        intervention_id=f"intervention-{suffix}",
        run_id=attempt.run_id,
        iteration_id=attempt.iteration_id,
        task_id=attempt.task_id,
        hypothesis_id=hypothesis.hypothesis_id,
        recall_snapshot_id=attempt.recall_snapshot_id,
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=proposal_digest,
        resolved_config=resolved_config,
        config_digest=config_digest,
        intervention_digest="b" * 64,
        manipulation_status="baseline",
        violations=[],
        created_at=NOW,
    )
    provenance = TrialProvenanceRecord(
        provenance_id=f"provenance-{suffix}",
        attempt_id=attempt.attempt_id,
        observation_id=observation.observation_id,
        intervention_id=intervention.intervention_id,
        proposal_digest=proposal_digest,
        intervention_digest=intervention.intervention_digest,
        source_digest="c" * 64,
        config_digest=config_digest,
        environment_digest="d" * 64,
        dataset_digest="e" * 64,
        contract_digest="f" * 64,
        evaluator_digest="0" * 64,
        attempt_spec_digest="1" * 64,
        evidence_digest="2" * 64,
        execution_envelope_ref=ArtifactRef(
            path="raw-evidence/attempt_spec.json",
            sha256="3" * 64,
            media_type="application/json",
            size_bytes=512,
        ),
        created_at=NOW + timedelta(seconds=4),
    )
    return intervention, provenance


def build_changed_intervention(records, *, previous_intervention_id: str):
    hypothesis, attempt, _, _, _, _ = records
    proposal = InterventionProposal(
        domain="vq",
        schema_id="vq.intervention@1",
        decision_point="optimizer",
        knob="projection_lr_multiplier",
        target=2.0,
        cited_knowledge_ids=["knowledge-prior"],
        expected_primary_metric_direction="increase",
        guardrail_risks=["unstable_optimizer"],
        rationale="Test the previously verified projection learning-rate lesson.",
    )
    resolved_config = {
        "learning_rate": 0.0003,
        "projection_lr_multiplier": 2.0,
        "seed": attempt.seed,
    }
    return InterventionRecord(
        intervention_id="intervention-changed",
        run_id=attempt.run_id,
        iteration_id="iteration-2",
        task_id=attempt.task_id,
        hypothesis_id=hypothesis.hypothesis_id,
        recall_snapshot_id=attempt.recall_snapshot_id,
        previous_intervention_id=previous_intervention_id,
        proposal=proposal,
        proposal_digest=semantic_digest(
            "ai-researcher/proposal/v1",
            proposal.model_dump(mode="json"),
        ),
        resolved_config=resolved_config,
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            resolved_config,
        ),
        intervention_digest="4" * 64,
        manipulation_status="changed",
        violations=[],
        created_at=NOW + timedelta(seconds=5),
    )


def test_ledger_contract_round_trips_and_queries(ledger):
    records = append_complete_record(ledger)
    experience = records[4]

    loaded = ledger.get_experience(experience.experience_id)
    queried = ledger.query(ExperienceQuery(task_id="task-vq", valid_only=True))

    assert loaded == experience
    assert queried == [experience]
    assert ledger.list_knowledge() == [records[5]]
    assert len(ledger.snapshot_id()) == 64


def test_in_memory_ledger_round_trips_sidecar_lineage():
    ledger = InMemoryExperimentLedger()
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)

    ledger.append_intervention(intervention)
    ledger.append_trial_provenance(provenance)

    assert ledger.get_intervention(intervention.intervention_id) == intervention
    assert ledger.list_interventions(intervention.run_id) == [intervention]
    assert (
        ledger.find_trial_provenance(provenance.observation_id)
        == provenance
    )


def test_ledger_contract_allows_only_one_intervention_per_iteration(ledger):
    records = append_complete_record(ledger)
    intervention, _ = build_sidecars(records)
    duplicate_iteration = intervention.model_copy(
        update={"intervention_id": "intervention-conflict"}
    )

    ledger.append_intervention(intervention)

    with pytest.raises(ImmutableRecordError, match="run-1.*iteration-1"):
        ledger.append_intervention(duplicate_iteration)


def test_ledger_contract_rejects_forged_content_derived_intervention_id(ledger):
    records = append_complete_record(ledger)
    intervention, _ = build_sidecars(records)
    forged = intervention.model_copy(update={"intervention_id": "0" * 64})

    with pytest.raises(ValueError, match="content-derived intervention_id"):
        ledger.append_intervention(forged)


def test_ledger_contract_requires_previous_intervention_lineage(ledger):
    records = append_complete_record(ledger)
    baseline, _ = build_sidecars(records)
    changed = build_changed_intervention(
        records,
        previous_intervention_id=baseline.intervention_id,
    ).model_copy(update={"recall_snapshot_id": "new-recall-snapshot"})

    with pytest.raises(RecordNotFoundError):
        ledger.append_intervention(changed)

    ledger.append_intervention(baseline)
    ledger.append_intervention(changed)

    assert ledger.list_interventions(baseline.run_id) == [baseline, changed]


@pytest.mark.parametrize(
    ("field", "other_value"),
    [
        ("run_id", "run-other"),
        ("task_id", "task-other"),
    ],
)
def test_ledger_contract_rejects_previous_intervention_from_other_lineage(
    ledger,
    field,
    other_value,
):
    records = append_complete_record(ledger)
    baseline, _ = build_sidecars(records)
    ledger.append_intervention(baseline)
    changed = build_changed_intervention(
        records,
        previous_intervention_id=baseline.intervention_id,
    ).model_copy(update={field: other_value})

    with pytest.raises(ValueError, match=field):
        ledger.append_intervention(changed)


def test_ledger_contract_allows_recalled_knowledge_to_revise_hypothesis(ledger):
    records = append_complete_record(ledger)
    baseline, _ = build_sidecars(records)
    ledger.append_intervention(baseline)
    revised = build_changed_intervention(
        records,
        previous_intervention_id=baseline.intervention_id,
    ).model_copy(
        update={
            "hypothesis_id": "hypothesis-revised-from-recall",
            "recall_snapshot_id": "snapshot-with-verified-negative",
        }
    )

    ledger.append_intervention(revised)

    assert ledger.list_interventions(baseline.run_id) == [baseline, revised]


def test_ledger_contract_rejects_nonadjacent_previous_intervention(ledger):
    records = append_complete_record(ledger)
    baseline, _ = build_sidecars(records)
    ledger.append_intervention(baseline)
    changed = build_changed_intervention(
        records,
        previous_intervention_id=baseline.intervention_id,
    ).model_copy(update={"iteration_id": "iteration-4"})

    with pytest.raises(ValueError, match="adjacent"):
        ledger.append_intervention(changed)


@pytest.mark.parametrize(
    "digest_field",
    ["proposal_digest", "intervention_digest", "config_digest"],
)
def test_ledger_contract_rejects_mismatched_trial_intervention_digests(
    ledger,
    digest_field,
):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="digests"):
        ledger.append_trial_provenance(
            provenance.model_copy(update={digest_field: "9" * 64})
        )


def test_ledger_contract_rejects_cross_run_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    intervention = intervention.model_copy(update={"run_id": "run-other"})
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="run_id"):
        ledger.append_trial_provenance(provenance)


def test_ledger_contract_rejects_cross_iteration_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    intervention = intervention.model_copy(update={"iteration_id": "iteration-other"})
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="iteration_id"):
        ledger.append_trial_provenance(provenance)


def test_ledger_contract_rejects_cross_task_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    intervention = intervention.model_copy(update={"task_id": "task-other"})
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="task_id"):
        ledger.append_trial_provenance(provenance)


def test_ledger_contract_rejects_cross_hypothesis_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    intervention = intervention.model_copy(
        update={"hypothesis_id": "hypothesis-other"}
    )
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="hypothesis_id"):
        ledger.append_trial_provenance(provenance)


def test_ledger_contract_rejects_cross_recall_snapshot_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    intervention = intervention.model_copy(
        update={"recall_snapshot_id": "snapshot-other"}
    )
    ledger.append_intervention(intervention)

    with pytest.raises(ValueError, match="recall_snapshot_id"):
        ledger.append_trial_provenance(provenance)


def test_ledger_contract_rejects_forged_content_derived_provenance_id(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    ledger.append_intervention(intervention)
    forged = provenance.model_copy(update={"provenance_id": "0" * 64})

    with pytest.raises(ValueError, match="content-derived provenance_id"):
        ledger.append_trial_provenance(forged)


def test_ledger_contract_rejects_rebound_trial_provenance(ledger):
    records = append_complete_record(ledger)
    intervention, provenance = build_sidecars(records)
    ledger.append_intervention(intervention)
    ledger.append_trial_provenance(provenance)
    ledger.append_trial_provenance(provenance)

    with pytest.raises(ImmutableRecordError, match="different content"):
        ledger.append_trial_provenance(
            provenance.model_copy(update={"evidence_digest": "8" * 64})
        )
    with pytest.raises(ImmutableRecordError, match="already has provenance"):
        ledger.append_trial_provenance(
            provenance.model_copy(update={"provenance_id": "provenance-other"})
        )


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


def test_sqlite_ledger_round_trips_sidecars_after_reopen(tmp_path):
    path = tmp_path / "experience.sqlite3"
    first = SQLiteExperimentLedger(path)
    records = append_complete_record(first)
    intervention, provenance = build_sidecars(records)

    first.append_intervention(intervention)
    first.append_trial_provenance(provenance)
    reopened = SQLiteExperimentLedger(path)

    assert reopened.get_intervention(intervention.intervention_id) == intervention
    assert reopened.list_interventions(intervention.run_id) == [intervention]
    assert (
        reopened.find_trial_provenance(provenance.observation_id)
        == provenance
    )
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2


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
