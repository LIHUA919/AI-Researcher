import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent.inno.experience import ExperienceQuery
from research_agent.runtime import (
    ExperienceConfigurationError,
    ExperienceRunAdapter,
    ProvidedIdeaStrategy,
    RunRequest,
)


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
    assert outcome.action == "invalid"
    assert outcome.reason == "attempt_failed"
    assert outcome.experience is not None
    assert outcome.experience.attempt.status == "failed"
    assert outcome.experience.observation.exit_code == 1
    assert len(adapter.ledger.query(ExperienceQuery(task_id="task-1"))) == 1
    assert adapter.ledger.list_knowledge() == []
