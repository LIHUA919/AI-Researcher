import json
from pathlib import Path

from research_agent.runtime import GoalDrivenSupervisor, MasterRuntime
from research_agent.runtime.master import StallEvaluation


class FakeProcess:
    def __init__(self, poll_sequence):
        self._poll_sequence = list(poll_sequence)
        self._index = 0
        self.terminated = False
        self.killed = False

    def poll(self):
        if self._index < len(self._poll_sequence):
            value = self._poll_sequence[self._index]
            self._index += 1
            return value
        return self._poll_sequence[-1] if self._poll_sequence else None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_goal_driven_supervisor_completes_when_goal_is_met(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    survey_stage = Path(tmp_dir) / "survey_stage"
    plan_stage = Path(tmp_dir) / "plan_stages"
    implement_stage = Path(tmp_dir) / "implement_stage"
    judge_stage = Path(tmp_dir) / "judge_stage"
    submit_stage = Path(tmp_dir) / "submit_stage"
    analyze_stage = Path(tmp_dir) / "analyze_stage"
    prepare_stage.mkdir()
    survey_stage.mkdir()
    plan_stage.mkdir()
    implement_stage.mkdir()
    judge_stage.mkdir()
    submit_stage.mkdir()
    analyze_stage.mkdir()
    (prepare_stage / "prepare_result.json").write_text("{}", encoding="utf-8")
    (survey_stage / "survey_result.json").write_text("{}", encoding="utf-8")
    for name in ("dataset_plan.json", "training_plan.json", "testing_plan.json", "plan_report.json"):
        (plan_stage / name).write_text("{}", encoding="utf-8")
    (implement_stage / "project_manifest.json").write_text("{}", encoding="utf-8")
    (judge_stage / "judge_report.json").write_text("{}", encoding="utf-8")
    (submit_stage / "submit_result.json").write_text("{}", encoding="utf-8")
    (analyze_stage / "analysis_report.json").write_text("{}", encoding="utf-8")

    runtime = MasterRuntime(tmp_dir)
    process = FakeProcess([None, None, None])
    supervisor = GoalDrivenSupervisor(
        runtime=runtime,
        run_id="run-complete",
        command=["python", "-c", "pass"],
        max_restarts=0,
        poll_interval_seconds=0,
        process_factory=lambda: process,
        sleep_fn=lambda _: None,
    )

    result = supervisor.run()

    run_status = json.loads((Path(tmp_dir) / "run_status.json").read_text(encoding="utf-8"))
    assert result.status == "completed"
    assert result.restart_count == 0
    assert run_status["status"] == "completed"
    assert result.events[0].event == "run_started"
    assert any(event.event == "run_completed" for event in result.events)


def test_goal_driven_supervisor_marks_stalled_after_restart_budget_exhausted(tmp_dir, monkeypatch):
    runtime = MasterRuntime(tmp_dir)
    processes = [FakeProcess([None]), FakeProcess([None])]

    def process_factory():
        return processes.pop(0)

    monkeypatch.setattr(
        runtime,
        "evaluate_stall",
        lambda max_stale_seconds: StallEvaluation(
            stalled=True,
            current_stage="prepare",
            age_seconds=600.0,
            reason="heartbeat_stale",
        ),
    )

    supervisor = GoalDrivenSupervisor(
        runtime=runtime,
        run_id="run-stalled",
        command=["python", "-c", "pass"],
        max_restarts=1,
        poll_interval_seconds=0,
        stale_timeout_seconds=300,
        process_factory=process_factory,
        sleep_fn=lambda _: None,
    )

    result = supervisor.run()

    run_status = json.loads((Path(tmp_dir) / "run_status.json").read_text(encoding="utf-8"))
    assert result.status == "stalled"
    assert result.restart_count == 1
    assert result.last_error == "heartbeat_stale"
    assert run_status["status"] == "stalled"
    assert any(event.event == "restart_scheduled" for event in result.events)
    assert any(event.event == "run_stalled" for event in result.events)
