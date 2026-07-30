import json
from pathlib import Path
from types import SimpleNamespace

from research_agent.inno.experience import ExperienceQuery
from research_agent.inno.experience import LoopOutcome, semantic_digest
from research_agent.runtime import (
    ExperienceRunAdapter,
    ImprovementCycleRequest,
    ImprovementCycleRunner,
    ProvidedIdeaStrategy,
    RunRequest,
)
from research_agent.runtime.adaptive_experiment import PreviousAttemptFeedback


CONTRACT_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmark"
    / "evaluators"
    / "deterministic_score"
    / "contract.yaml"
)


def _closed_loop_args(tmp_path):
    return SimpleNamespace(
        experience_mode="closed-loop",
        experience_store=str(tmp_path / "experience.sqlite3"),
        evaluation_contract=str(CONTRACT_PATH),
        max_loop_iterations=2,
        recall_item_budget=8,
        recall_token_budget=3000,
    )


def test_closed_loop_runs_isolated_attempts_and_recalls_verified_failure(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    adapter = ExperienceRunAdapter.from_args(
        _closed_loop_args(tmp_path),
        cache_path=tmp_path / "run-cache",
    )
    request = ImprovementCycleRequest(
        run_id="run-1",
        task_id="task-1",
        query="increase score",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        project_dir=project,
        run_cache_path=tmp_path / "run-cache",
        seed=17,
    )
    attempts = []

    def run_attempt(context):
        attempts.append(context)
        score = 0.8 if context.recall_context.items else 0.4
        (project / "metrics.json").write_text(
            f'{{"score": {score}}}',
            encoding="utf-8",
        )
        (project / "run.log").write_text(
            f"iteration={context.iteration_number}",
            encoding="utf-8",
        )
        run_request = RunRequest(
            run_id=request.run_id,
            task_id=request.task_id,
            entrypoint="test",
            task_level="task1",
            model=request.model,
            workplace_name="workplace",
            cache_path=str(context.attempt_cache_path),
            intent=request.query,
            conditions=[request.domain],
        )
        hypothesis = ProvidedIdeaStrategy().build_hypothesis(
            run_request,
            context.recall_context,
        )
        return {
            "task_id": request.task_id,
            "query": request.query,
            "analysis": f"verified score={score}",
            "metadata": {
                "hypothesis": hypothesis.model_dump(mode="json"),
                "llm_usage": {
                    "calls": context.iteration_number,
                    "prompt_tokens": context.iteration_number * 10,
                    "completion_tokens": context.iteration_number * 5,
                    "total_tokens": context.iteration_number * 15,
                    "by_model": {
                        "test-model": {
                            "calls": context.iteration_number,
                            "prompt_tokens": context.iteration_number * 10,
                            "completion_tokens": context.iteration_number * 5,
                            "total_tokens": context.iteration_number * 15,
                        }
                    },
                },
            },
        }

    result = ImprovementCycleRunner(adapter).run(request, run_attempt)

    assert result.outcome is not None
    assert result.outcome.action == "completed"
    assert [attempt.iteration_number for attempt in attempts] == [1, 2]
    assert [attempt.attempt_cache_path for attempt in attempts] == [
        tmp_path / "run-cache" / "attempts" / "iteration-001",
        tmp_path / "run-cache" / "attempts" / "iteration-002",
    ]
    assert attempts[0].recall_context.items == []
    assert attempts[1].recall_context.items[0].outcome == "negative"
    assert attempts[1].recall_context.items[0].citation_id.startswith("knowledge:")
    experiences = list(
        reversed(adapter.ledger.query(ExperienceQuery(task_id=request.task_id)))
    )
    assert len(experiences) == 2
    assert [experience.attempt.seed for experience in experiences] == [17, 17]
    assert experiences[1].hypothesis.parent_experience_ids == [
        experiences[0].experience_id
    ]
    first_metrics_ref = next(
        ref
        for ref in experiences[0].observation.artifact_refs
        if Path(ref.path).name == "metrics.json"
    )
    second_metrics_ref = next(
        ref
        for ref in experiences[1].observation.artifact_refs
        if Path(ref.path).name == "metrics.json"
    )
    assert first_metrics_ref.path != second_metrics_ref.path
    assert json.loads(Path(first_metrics_ref.path).read_text())["score"] == 0.4
    assert json.loads(Path(second_metrics_ref.path).read_text())["score"] == 0.8
    assert Path(result.attempt_cache_path) == attempts[1].attempt_cache_path
    assert result.flow_result["metadata"]["llm_usage"]["calls"] == 3
    assert result.flow_result["metadata"]["llm_usage"]["total_tokens"] == 45
    assert result.flow_result["metadata"]["llm_usage"]["by_model"]["test-model"][
        "total_tokens"
    ] == 45
    assert [
        item["iteration_number"]
        for item in result.flow_result["metadata"]["attempt_llm_usage"]
    ] == [1, 2]


def test_closed_loop_retries_runtime_failure_with_isolated_attempt(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    adapter = ExperienceRunAdapter.from_args(
        _closed_loop_args(tmp_path),
        cache_path=tmp_path / "run-cache",
    )
    request = ImprovementCycleRequest(
        run_id="run-failure",
        task_id="task-failure",
        query="recover from implementation failure",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        project_dir=project,
        run_cache_path=tmp_path / "run-cache",
        seed=23,
    )
    attempts = []

    def run_attempt(context):
        attempts.append(context)
        if context.iteration_number == 1:
            raise RuntimeError("implementation guardrail failed")
        assert context.attempt_cache_path.name == "iteration-002"
        (project / "metrics.json").write_text(
            '{"score": 0.8}',
            encoding="utf-8",
        )
        (project / "run.log").write_text("recovered", encoding="utf-8")
        run_request = RunRequest(
            run_id=request.run_id,
            task_id=request.task_id,
            entrypoint="test",
            task_level="task1",
            model=request.model,
            workplace_name="workplace",
            cache_path=str(context.attempt_cache_path),
            intent=request.query,
            conditions=[request.domain],
        )
        hypothesis = ProvidedIdeaStrategy().build_hypothesis(
            run_request,
            context.recall_context,
        )
        return {
            "task_id": request.task_id,
            "query": request.query,
            "analysis": "recovered",
            "metadata": {
                "hypothesis": hypothesis.model_dump(mode="json"),
            },
        }

    result = ImprovementCycleRunner(adapter).run(request, run_attempt)

    assert [attempt.iteration_number for attempt in attempts] == [1, 2]
    assert result.iteration_number == 2
    assert result.outcome is not None
    assert result.outcome.action == "completed"
    experiences = adapter.ledger.query(
        ExperienceQuery(task_id=request.task_id),
    )
    assert len(experiences) == 2
    assert {item.attempt.status for item in experiences} == {
        "failed",
        "completed",
    }


def test_control_iterations_reuse_immutable_semantic_hypothesis(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    args = _closed_loop_args(tmp_path)
    args.recall_item_budget = 0
    args.recall_token_budget = 0
    adapter = ExperienceRunAdapter.from_args(
        args,
        cache_path=tmp_path / "run-cache",
    )
    request = ImprovementCycleRequest(
        run_id="run-control",
        task_id="task-control",
        query="measure the unchanged control",
        model="test-model",
        domain="test-domain",
        dataset_id="test-data",
        model_family="test-model",
        project_dir=project,
        run_cache_path=tmp_path / "run-cache",
        seed=29,
    )

    def run_attempt(context):
        (project / "metrics.json").write_text(
            '{"score": 0.4}',
            encoding="utf-8",
        )
        (project / "run.log").write_text(
            f"iteration={context.iteration_number}",
            encoding="utf-8",
        )
        hypothesis = ProvidedIdeaStrategy().build_hypothesis(
            RunRequest(
                run_id=request.run_id,
                task_id=request.task_id,
                entrypoint="test",
                task_level="task1",
                model=request.model,
                workplace_name="workplace",
                cache_path=str(context.attempt_cache_path),
                intent=request.query,
                conditions=[request.domain],
            ),
            context.recall_context,
        )
        return {
            "task_id": request.task_id,
            "query": request.query,
            "analysis": "unchanged control",
            "metadata": {"hypothesis": hypothesis.model_dump(mode="json")},
        }

    result = ImprovementCycleRunner(adapter).run(request, run_attempt)

    assert result.outcome is not None
    assert result.outcome.action == "failed_budget"
    experiences = list(
        reversed(adapter.ledger.query(ExperienceQuery(task_id=request.task_id)))
    )
    assert len(experiences) == 2
    assert len({item.hypothesis.hypothesis_id for item in experiences}) == 1
    assert len({item.hypothesis.created_at for item in experiences}) == 1


class _FeedbackCarryingAdapter:
    max_iterations = 2
    runs_closed_loop = True
    records_experience = True

    def before_run(self, **kwargs):
        return None

    def pending_verification_check(self):
        return None

    def after_flow(self, flow_result, **kwargs):
        return LoopOutcome(
            action=(
                "continue"
                if kwargs["iteration_number"] == 1
                else "completed"
            )
        )

    def build_previous_feedback(self, flow_result, outcome):
        return flow_result.get("verified_feedback")

    def finalize_runtime(self, **kwargs):
        return None


def test_cycle_carries_only_verified_typed_feedback_to_next_attempt(tmp_path):
    adapter = _FeedbackCarryingAdapter()
    request = ImprovementCycleRequest(
        run_id="run-feedback",
        task_id="task-feedback",
        query="improve",
        model="model",
        domain="vq",
        dataset_id="cifar10",
        model_family="model",
        project_dir=tmp_path / "project",
        run_cache_path=tmp_path / "cache",
        seed=401,
    )
    effective_config = {"commitment_weight": 0.25}
    feedback = PreviousAttemptFeedback(
        attempt_id="attempt-1",
        intervention_id="intervention-1",
        config_digest=semantic_digest(
            "ai-researcher/run-config/v1",
            effective_config,
        ),
        effective_config=effective_config,
        verified_metrics={"codebook_utilization": 0.2},
        outcome="negative",
        guardrail_violations=[],
    )
    seen = []

    def run_attempt(context):
        seen.append(context.previous_feedback)
        return {
            "metadata": {},
            "verified_feedback": feedback,
        }

    result = ImprovementCycleRunner(adapter).run(request, run_attempt)

    assert result.iteration_number == 2
    assert seen == [None, feedback]
