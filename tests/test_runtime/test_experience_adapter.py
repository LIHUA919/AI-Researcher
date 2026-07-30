import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent.inno.experience import (
    ExperienceQuery,
    Hypothesis,
    InterventionProposal,
    InterventionRecord,
    evaluator_identity,
    load_evaluation_contract,
    semantic_digest,
)
from research_agent.runtime import (
    ExperienceConfigurationError,
    ExperienceRunAdapter,
    ProvidedIdeaStrategy,
    RunRequest,
)
from research_agent.runtime.adaptive_experiment import (
    AdaptiveExperimentResult,
    TrialPreflight,
    TrialReceipt,
)
from research_agent.runtime.trial_provenance import artifact_ref, content_digest


CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmark"
    / "evaluators"
    / "deterministic_score"
    / "contract.yaml"
)


def _flow_result(tmp_path, recall=None):
    request = RunRequest(
        run_id="run-1",
        task_id="task-1",
        entrypoint="test",
        task_level="task1",
        model="test-model",
        workplace_name="workplace",
        cache_path=str(tmp_path / "cache"),
        intent="Increase the deterministic score.",
        conditions=["test-domain"],
    )
    hypothesis = ProvidedIdeaStrategy().build_hypothesis(request, recall)
    return {
        "task_id": "task-1",
        "query": "increase score",
        "analysis": "Use this configuration because it improves the score.",
        "final_output": {"submission_report": "score improved"},
        "metadata": {"hypothesis": hypothesis.model_dump(mode="json")},
    }


def _args(tmp_path, *, mode="closed-loop", contract=CONTRACT_PATH):
    return SimpleNamespace(
        experience_mode=mode,
        experience_store=str(tmp_path / "experience.sqlite3"),
        evaluation_contract=str(contract) if contract is not None else None,
        max_loop_iterations=2,
        recall_item_budget=8,
        recall_token_budget=3000,
    )


def _project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "metrics.json").write_text('{"score": 0.8}', encoding="utf-8")
    (project / "run.log").write_text("deterministic run", encoding="utf-8")
    return project


def test_recording_mode_requires_independent_evaluation_contract(tmp_path):
    with pytest.raises(ExperienceConfigurationError):
        ExperienceRunAdapter.from_args(
            _args(tmp_path, contract=None),
            cache_path=tmp_path / "cache",
        )


def test_off_mode_is_a_no_op(tmp_path):
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path, mode="off", contract=None),
        cache_path=tmp_path / "cache",
    )

    assert (
        adapter.before_run(
            task_id="task-1",
            query="score",
            domain="test-domain",
            dataset_id="test-data",
            model_family="test-model",
        )
        is None
    )
    assert adapter.verification_check("run-1") is None
    assert adapter.pending_verification_check() is None


def test_entrypoint_adapter_persists_verifies_recalls_and_restarts(tmp_path):
    project = _project(tmp_path)
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path),
        cache_path=tmp_path / "cache",
    )
    recall = adapter.before_run(
        task_id="task-1",
        query="increase score",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
    )
    assert recall is not None
    assert recall.items == []

    flow_result = _flow_result(tmp_path, recall)
    outcome = adapter.after_flow(
        flow_result,
        project_dir=project,
        run_id="run-1",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        recall_context=recall,
        iteration_number=1,
    )

    assert outcome is not None
    assert outcome.action == "completed"
    assert outcome.verification is not None
    assert outcome.verification.valid is True
    assert adapter.verification_check("run-1")()
    assert adapter.pending_verification_check()() is False
    assert (tmp_path / "cache" / "experience_outcome.json").is_file()
    adapter.finalize_runtime(run_id="run-1", outcome=outcome)
    runtime_status = json.loads(
        (tmp_path / "cache" / "run_status.json").read_text(encoding="utf-8")
    )
    assert runtime_status["status"] == "completed"

    repeated = adapter.after_flow(
        flow_result,
        project_dir=project,
        run_id="run-1",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        recall_context=recall,
        iteration_number=1,
    )
    assert repeated == outcome

    reopened = ExperienceRunAdapter.from_args(
        _args(tmp_path),
        cache_path=tmp_path / "cache",
    )
    recalled = reopened.before_run(
        task_id="task-1",
        query="increase score",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
    )
    assert recalled is not None
    assert len(recalled.items) == 1
    assert recalled.items[0].outcome == "positive"
    assert len(reopened.ledger.list_knowledge()) == 1
    assert len(reopened.ledger.list_promotion_decisions()) == 1


def test_entrypoint_adapter_closes_negative_to_positive_iteration(tmp_path):
    project = _project(tmp_path)
    (project / "metrics.json").write_text('{"score": 0.4}', encoding="utf-8")
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path),
        cache_path=tmp_path / "cache",
    )
    first_recall = adapter.before_run(
        task_id="task-1",
        query="increase score",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
    )
    first = adapter.after_flow(
        _flow_result(tmp_path, first_recall),
        project_dir=project,
        run_id="run-1",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        recall_context=first_recall,
        iteration_number=1,
    )
    assert first is not None
    assert first.action == "continue"

    second_recall = adapter.before_run(
        task_id="task-1",
        query="increase score",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
    )
    assert second_recall.items[0].outcome == "negative"
    (project / "metrics.json").write_text('{"score": 0.8}', encoding="utf-8")
    second = adapter.after_flow(
        _flow_result(tmp_path, second_recall),
        project_dir=project,
        run_id="run-1",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        recall_context=second_recall,
        iteration_number=2,
    )

    assert second is not None
    assert second.action == "completed"
    assert second.experience is not None
    assert second.experience.hypothesis.parent_experience_ids == [
        first.experience.experience_id
    ]


def test_entrypoint_adapter_retains_failure_without_promoting_it(tmp_path):
    project = _project(tmp_path)
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path),
        cache_path=tmp_path / "cache",
    )
    recall = adapter.before_run(
        task_id="task-1",
        query="increase score",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
    )

    outcome = adapter.after_failure(
        project_dir=project,
        run_id="run-1",
        task_id="task-1",
        query="increase score",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        recall_context=recall,
        iteration_number=1,
        error=RuntimeError("training crashed"),
    )

    assert outcome is not None
    assert outcome.action == "continue"
    assert outcome.reason == "attempt_failed"
    assert outcome.experience is not None
    assert outcome.experience.attempt.status == "failed"
    assert outcome.experience.observation.exit_code == 1
    assert len(adapter.ledger.query(ExperienceQuery(task_id="task-1"))) == 1
    assert adapter.ledger.list_knowledge() == []


def _v3_contract(tmp_path):
    contract_dir = tmp_path / "contract"
    contract_dir.mkdir()
    (contract_dir / "evaluate.py").write_text(
        """
import json
import sys
from pathlib import Path

Path(sys.argv[1], "verification_result.json").write_text(
    json.dumps({"metrics": {"score": 0.8}, "repetitions": 1}),
    encoding="utf-8",
)
""".strip(),
        encoding="utf-8",
    )
    contract = {
        "schema_version": 2,
        "contract_id": "adaptive-test",
        "version": "3",
        "task_id": "task-v3",
        "entrypoint": 'python evaluate.py "{attempt_dir}"',
        "result_file": "verification_result.json",
        "required_artifacts": [
            "attempt_spec.json",
            "evaluation_manifest.json",
            "evaluation_arrays.npz",
            "run.log",
        ],
        "evaluator_files": ["evaluate.py"],
        "primary_metric": {"name": "score", "direction": "maximize"},
        "baseline": 0.5,
        "adaptive_experiment": {
            "policy_id": "adaptive-test-policy",
            "version": "1",
            "decision_point": "test.gain",
            "no_op_policy": "reject_before_execution",
            "max_changes_per_attempt": 1,
            "defaults": {"gain": 1.0},
            "knobs": {
                "gain": {
                    "value_type": "number",
                    "allowed_values": [0.5, 1.0, 2.0],
                }
            },
            "fixed_config": {"dataset_id": "cifar10"},
            "source_files": ["source.py"],
            "expected_source_digest": "a" * 64,
        },
    }
    path = contract_dir / "contract.json"
    path.write_text(json.dumps(contract), encoding="utf-8")
    return path


def _baseline_adaptive_result(tmp_path, hypothesis, contract_path):
    evidence = tmp_path / "raw-evidence"
    evidence.mkdir()
    for name, content in {
        "attempt_spec.json": b'{"schema_version":1}',
        "evaluation_manifest.json": b'{"schema_version":2}',
        "evaluation_arrays.npz": b"array-evidence",
        "run.log": b"completed",
    }.items():
        (evidence / name).write_bytes(content)
    refs = [
        artifact_ref(evidence / name)
        for name in (
            "attempt_spec.json",
            "evaluation_manifest.json",
            "evaluation_arrays.npz",
            "run.log",
        )
    ]
    proposal = InterventionProposal(
        domain="test",
        schema_id="adaptive-test@1",
        decision_point="test.gain",
        knob=None,
        target=None,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="System-owned baseline.",
    )
    proposal_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        proposal.model_dump(mode="json"),
    )
    config = {
        "dataset_id": "cifar10",
        "gain": 1.0,
        "seed": 401,
        "resolved_device": "cpu",
    }
    config_digest = semantic_digest("ai-researcher/run-config/v1", config)
    attempt_spec_digest = semantic_digest(
        "ai-researcher/attempt-spec/v1",
        json.loads((evidence / "attempt_spec.json").read_text(encoding="utf-8")),
    )
    intervention_digest = semantic_digest(
        "ai-researcher/intervention/v1",
        {"gain": 1.0},
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    contract_digest = content_digest(
        "ai-researcher/contract/v1",
        contract_path.read_bytes(),
    )
    evaluator_digest = evaluator_identity(
        load_evaluation_contract(contract_path),
        contract_path.parent,
    )
    intervention = InterventionRecord(
        intervention_id="intervention-v3-baseline",
        run_id="run-v3",
        iteration_id="iteration-001",
        task_id="task-v3",
        hypothesis_id=hypothesis.hypothesis_id,
        recall_snapshot_id="off",
        previous_intervention_id=None,
        proposal=proposal,
        proposal_digest=proposal_digest,
        resolved_config=config,
        config_digest=config_digest,
        intervention_digest=intervention_digest,
        manipulation_status="baseline",
        violations=[],
        created_at=now,
    )
    preflight = TrialPreflight(
        attempt_key="run-v3:iteration-001",
        proposal_digest=proposal_digest,
        intervention_digest=intervention_digest,
        config_digest=config_digest,
        source_digest="a" * 64,
        dataset_digest="b" * 64,
        environment_digest="c" * 64,
        contract_digest=contract_digest,
        evaluator_digest=evaluator_digest,
        attempt_spec_digest=attempt_spec_digest,
        effective_config=config,
        manipulation_status="baseline",
    )
    receipt = TrialReceipt(
        attempt_spec_ref=refs[0],
        manifest_ref=refs[1],
        artifact_refs=refs,
        actual_config=config,
        proposal_digest=proposal_digest,
        intervention_digest=intervention_digest,
        config_digest=config_digest,
        source_digest="a" * 64,
        dataset_digest="b" * 64,
        environment_digest="c" * 64,
        contract_digest=contract_digest,
        evaluator_digest=evaluator_digest,
        evidence_payload_digest="1" * 64,
        started_at=now,
        completed_at=now,
        exit_code=0,
    )
    return AdaptiveExperimentResult(
        status="executed",
        intervention=intervention,
        preflight=preflight,
        receipt=receipt,
    )


def test_v3_adapter_uses_typed_receipt_and_binds_trial_provenance(tmp_path):
    contract_path = _v3_contract(tmp_path)
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path, contract=contract_path),
        cache_path=tmp_path / "cache",
    )
    hypothesis = Hypothesis(
        hypothesis_id="hypothesis-v3",
        task_id="task-v3",
        statement="Measure a governed baseline.",
        mechanism="The baseline fixes all catalog defaults.",
        expected_metric="score",
        metric_direction="maximize",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    adaptive = _baseline_adaptive_result(tmp_path, hypothesis, contract_path)
    adapter.ledger.append_intervention(adaptive.intervention)
    flow_result = {
        "task_id": "task-v3",
        "analysis": "Externally verify the governed baseline.",
        "metadata": {
            "hypothesis": hypothesis.model_dump(mode="json"),
            "adaptive_experiment": adaptive.model_dump(mode="json"),
        },
    }

    outcome = adapter.after_flow(
        flow_result,
        project_dir=tmp_path / "project",
        run_id="run-v3",
        model="research-model",
        domain="test",
        dataset_id="cifar10",
        model_family="research-model",
        recall_context=None,
        iteration_number=1,
        seed=401,
    )

    assert outcome is not None
    assert outcome.experience is not None
    assert outcome.experience.attempt.code_revision == "a" * 64
    assert outcome.experience.attempt.dataset_digest == "b" * 64
    assert outcome.experience.observation.metrics == {}
    assert {
        Path(ref.path).name
        for ref in outcome.experience.observation.artifact_refs
    } == set(adapter.contract.required_artifacts)
    provenance = adapter.ledger.find_trial_provenance(
        outcome.experience.observation.observation_id
    )
    assert provenance is not None
    assert provenance.intervention_id == adaptive.intervention.intervention_id
    assert (
        Path(provenance.execution_envelope_ref.path).name
        == "attempt_spec.json"
    )
    feedback = adapter.build_previous_feedback(flow_result, outcome)
    assert feedback is not None
    assert feedback.attempt_id == outcome.experience.attempt.attempt_id
    assert feedback.intervention_id == adaptive.intervention.intervention_id
    assert feedback.verified_metrics == {"score": 0.8}
    assert adapter.ledger.list_knowledge() == []


def test_v3_rejected_no_effect_does_not_create_fake_attempt(tmp_path):
    contract_path = _v3_contract(tmp_path)
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path, contract=contract_path),
        cache_path=tmp_path / "cache",
    )
    hypothesis = Hypothesis(
        hypothesis_id="hypothesis-v3-no-effect",
        task_id="task-v3",
        statement="Do not rerun an unchanged assignment.",
        mechanism="The governed target equals the previous effective value.",
        expected_metric="score",
        metric_direction="maximize",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    baseline = _baseline_adaptive_result(
        tmp_path,
        hypothesis,
        contract_path,
    )
    previous = baseline.intervention.model_copy(
        update={
            "intervention_id": "intervention-v3-previous",
            "hypothesis_id": hypothesis.hypothesis_id,
        }
    )
    proposal = InterventionProposal(
        domain="test",
        schema_id="adaptive-test@1",
        decision_point="test.gain",
        knob="gain",
        target=1.0,
        cited_knowledge_ids=[],
        expected_primary_metric_direction="unchanged",
        guardrail_risks=[],
        rationale="The target deliberately matches the previous assignment.",
    )
    proposal_digest = semantic_digest(
        "ai-researcher/proposal/v1",
        proposal.model_dump(mode="json"),
    )
    rejected = baseline.intervention.model_copy(
        update={
            "intervention_id": "intervention-v3-no-effect",
            "iteration_id": "iteration-002",
            "hypothesis_id": hypothesis.hypothesis_id,
            "previous_intervention_id": previous.intervention_id,
            "proposal": proposal,
            "proposal_digest": proposal_digest,
            "manipulation_status": "no_effect",
        }
    )
    preflight = baseline.preflight.model_copy(
        update={
            "attempt_key": "run-v3:iteration-002",
            "proposal_digest": proposal_digest,
            "manipulation_status": "no_effect",
        }
    )
    adaptive = AdaptiveExperimentResult(
        status="rejected_no_effect",
        intervention=rejected,
        preflight=preflight,
        receipt=None,
    )
    adapter.ledger.append_intervention(previous)
    adapter.ledger.append_intervention(rejected)

    outcome = adapter.after_flow(
        {
            "metadata": {
                "adaptive_experiment": adaptive.model_dump(mode="json"),
            }
        },
        project_dir=tmp_path / "project",
        run_id="run-v3",
        model="research-model",
        domain="test",
        dataset_id="cifar10",
        model_family="research-model",
        recall_context=None,
        iteration_number=2,
        seed=401,
    )

    assert outcome is not None
    assert outcome.action == "manipulation_failed"
    assert adapter.ledger.query(ExperienceQuery(task_id="task-v3")) == []
    assert adapter.ledger.list_promotion_decisions() == []


def test_v3_execution_error_without_receipt_is_not_backfilled_as_a_trial(
    tmp_path,
):
    adapter = ExperienceRunAdapter.from_args(
        _args(tmp_path, contract=_v3_contract(tmp_path)),
        cache_path=tmp_path / "cache",
    )

    outcome = adapter.after_failure(
        project_dir=tmp_path / "project",
        run_id="run-v3",
        task_id="task-v3",
        query="execute governed attempt",
        model="research-model",
        domain="test",
        dataset_id="cifar10",
        model_family="research-model",
        recall_context=None,
        iteration_number=1,
        error=RuntimeError("subprocess failed before a receipt existed"),
        seed=401,
    )

    assert outcome is None
    assert adapter.ledger.query(ExperienceQuery(task_id="task-v3")) == []
