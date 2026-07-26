from pathlib import Path
from types import SimpleNamespace

import pytest

from research_agent.runtime.run_orchestrator import (
    ResearchRunLaunch,
    ResearchRunOrchestrator,
)


class FakeExecution:
    def __init__(self, root: Path, *, fail: bool = False) -> None:
        self.cache_path = root / "cache"
        self.project_dir = root / "project"
        self.cache_path.mkdir()
        self.project_dir.mkdir()
        self.fail = fail
        self.calls = []

    def execute(self, *, recall_context, verification_check):
        self.calls.append((recall_context, verification_check))
        if self.fail:
            raise RuntimeError("execution failed")
        return {"iteration": len(self.calls)}

    def build_result(self, result):
        return {"result": result}


class FakeExperience:
    def __init__(self, *, actions, records_experience=True) -> None:
        self.max_iterations = len(actions)
        self.runs_closed_loop = len(actions) > 1
        self.records_experience = records_experience
        self.actions = list(actions)
        self.recalls = []
        self.recorded = []
        self.failures = []
        self.finalized = []

    def before_run(self, **request):
        context = SimpleNamespace(
            snapshot_id=f"snapshot-{len(self.recalls) + 1}",
            request=request,
        )
        self.recalls.append(context)
        return context

    @staticmethod
    def pending_verification_check():
        return "verification-check"

    def after_flow(self, result, **metadata):
        action = self.actions.pop(0)
        outcome = SimpleNamespace(
            action=action,
            model_dump=lambda **_: {"action": action},
        )
        self.recorded.append((result, metadata))
        return outcome

    def after_failure(self, **metadata):
        self.failures.append(metadata)
        return SimpleNamespace(action="invalid")

    def finalize_runtime(self, **metadata):
        self.finalized.append(metadata)


def launch(entrypoint: str = "run_infer_plan") -> ResearchRunLaunch:
    return ResearchRunLaunch(
        run_id="run-1",
        task_id="task-1",
        query="improve the score",
        entrypoint=entrypoint,
        task_level="task1",
        model="fixture-model",
        domain="vq",
        dataset_id="fixture-data",
    )


@pytest.mark.parametrize("entrypoint", ["run_infer_plan", "run_infer_idea"])
def test_both_entrypoints_cross_the_same_orchestrator(tmp_path, entrypoint):
    execution = FakeExecution(tmp_path)
    experience = FakeExperience(actions=["continue", "completed"])

    bundle = ResearchRunOrchestrator(
        experience=experience,
        execution=execution,
    ).run(launch(entrypoint))

    assert len(execution.calls) == 2
    assert len(experience.recalls) == 2
    assert len(experience.recorded) == 2
    assert bundle["result"] == {"iteration": 2}
    assert bundle["experience_outcome"] == {"action": "completed"}


def test_execution_failure_is_recorded_once_before_status_is_written(tmp_path):
    execution = FakeExecution(tmp_path, fail=True)
    experience = FakeExperience(actions=["completed"])

    with pytest.raises(RuntimeError, match="execution failed"):
        ResearchRunOrchestrator(
            experience=experience,
            execution=execution,
        ).run(launch())

    assert len(experience.failures) == 1
    assert experience.failures[0]["iteration_number"] == 1
    assert len(experience.finalized) == 1
