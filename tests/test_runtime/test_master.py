import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_agent.runtime import MasterRuntime, validate_stage_artifacts


def test_validate_stage_artifacts_detects_completed_plan_stage(tmp_dir):
    plan_stage = Path(tmp_dir) / "plan_stages"
    plan_stage.mkdir()
    for name in ("dataset_plan.json", "training_plan.json", "testing_plan.json", "plan_report.json"):
        (plan_stage / name).write_text("{}", encoding="utf-8")

    evaluation = validate_stage_artifacts(tmp_dir, "plan")

    assert evaluation["completed"] is True
    assert evaluation["missing_artifacts"] == []


def test_master_runtime_returns_next_incomplete_stage(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    prepare_stage.mkdir()
    (prepare_stage / "prepare_result.json").write_text("{}", encoding="utf-8")

    runtime = MasterRuntime(tmp_dir)
    goal = runtime.evaluate_goal()

    assert goal.completed_stages == ["prepare"]
    assert goal.current_stage == "survey"
    assert runtime.should_run_stage("survey") is True


def test_master_runtime_syncs_completed_stage_state(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    survey_stage = Path(tmp_dir) / "survey_stage"
    prepare_stage.mkdir()
    survey_stage.mkdir()
    (prepare_stage / "prepare_result.json").write_text("{}", encoding="utf-8")
    (survey_stage / "survey_result.json").write_text(
        json.dumps({"survey_report": "done"}),
        encoding="utf-8",
    )

    runtime = MasterRuntime(tmp_dir)
    state = runtime.sync_stage_state()

    assert state["prepare"]["status"] == "completed"
    assert state["survey"]["status"] == "completed"
    assert runtime.next_stage() == "plan"


def test_master_runtime_evaluates_goal_progress(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    survey_stage = Path(tmp_dir) / "survey_stage"
    prepare_stage.mkdir()
    survey_stage.mkdir()
    (prepare_stage / "prepare_result.json").write_text("{}", encoding="utf-8")
    (survey_stage / "survey_result.json").write_text("{}", encoding="utf-8")

    runtime = MasterRuntime(tmp_dir)
    runtime.sync_stage_state()
    goal = runtime.evaluate_goal()

    assert goal.current_stage == "plan"
    assert goal.completed_stages == ["prepare", "survey"]
    assert "plan" in goal.incomplete_stages
    assert goal.all_criteria_met is False


def test_master_runtime_can_run_only_after_previous_stages_complete(tmp_dir):
    runtime = MasterRuntime(tmp_dir)
    assert runtime.can_run_stage("prepare") is True
    assert runtime.can_run_stage("survey") is False

    prepare_stage = Path(tmp_dir) / "prepare_stage"
    prepare_stage.mkdir()
    (prepare_stage / "prepare_result.json").write_text("{}", encoding="utf-8")
    runtime.sync_stage_state()

    assert runtime.can_run_stage("survey") is True
    assert runtime.can_run_stage("plan") is False


def test_master_runtime_record_stage_completion_persists_state(tmp_dir):
    runtime = MasterRuntime(tmp_dir)
    state = runtime.record_stage_completion(
        "prepare",
        artifacts={"prepare_result": f"{tmp_dir}/prepare_stage/prepare_result.json"},
        metadata={"source": "runtime"},
    )

    assert state["prepare"]["status"] == "completed"
    assert state["prepare"]["metadata"]["source"] == "runtime"


def test_master_runtime_writes_heartbeat_and_run_status(tmp_dir):
    prepare_stage = Path(tmp_dir) / "prepare_stage"
    prepare_stage.mkdir()
    prepare_result = prepare_stage / "prepare_result.json"
    prepare_result.write_text("{}", encoding="utf-8")

    runtime = MasterRuntime(tmp_dir)
    runtime.sync_stage_state()
    outputs = runtime.write_runtime_status(run_id="run-1", status="running")

    heartbeat_payload = json.loads(Path(outputs["heartbeat"]).read_text(encoding="utf-8"))
    run_status_payload = json.loads(Path(outputs["run_status"]).read_text(encoding="utf-8"))

    assert heartbeat_payload["status"] == "running"
    assert heartbeat_payload["current_stage"] == "survey"
    assert run_status_payload["run_id"] == "run-1"
    assert run_status_payload["current_stage"] == "survey"
    assert run_status_payload["latest_artifact"].endswith("prepare_result.json")


def test_master_runtime_writes_failure_status(tmp_dir):
    runtime = MasterRuntime(tmp_dir)
    outputs = runtime.write_failure_status(
        run_id="run-2",
        error_message="llm timeout",
        stage_name="survey",
        metadata={"source": "test"},
    )

    run_status_payload = json.loads(Path(outputs["run_status"]).read_text(encoding="utf-8"))
    heartbeat_payload = json.loads(Path(outputs["heartbeat"]).read_text(encoding="utf-8"))
    state_payload = runtime.load_state()

    assert run_status_payload["status"] == "failed"
    assert run_status_payload["last_error"] == "llm timeout"
    assert heartbeat_payload["status"] == "failed"
    assert state_payload["survey"]["status"] == "failed"
    assert state_payload["survey"]["metadata"]["last_error"] == "llm timeout"
    failure_report = json.loads(Path(outputs["failure_report"]).read_text(encoding="utf-8"))
    assert failure_report["status"] == "failed"
    assert failure_report["stage"] == "survey"
    assert failure_report["error_message"] == "llm timeout"


def test_master_runtime_evaluates_stall_from_stale_heartbeat(tmp_dir):
    runtime = MasterRuntime(tmp_dir)
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    heartbeat_path = Path(tmp_dir) / "heartbeat.json"
    heartbeat_path.write_text(
        json.dumps(
            {
                "current_stage": "implement",
                "status": "running",
                "updated_at": stale_time,
                "last_error": None,
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )

    evaluation = runtime.evaluate_stall(max_stale_seconds=300)

    assert evaluation.stalled is True
    assert evaluation.current_stage == "implement"
    assert evaluation.reason == "heartbeat_stale"
    assert evaluation.age_seconds is not None
    assert evaluation.age_seconds >= 300


def test_master_runtime_writes_stalled_status(tmp_dir):
    runtime = MasterRuntime(tmp_dir)
    outputs = runtime.write_stalled_status(
        run_id="run-3",
        reason="no_heartbeat_progress",
        stage_name="implement",
        metadata={"source": "monitor"},
    )

    run_status_payload = json.loads(Path(outputs["run_status"]).read_text(encoding="utf-8"))
    heartbeat_payload = json.loads(Path(outputs["heartbeat"]).read_text(encoding="utf-8"))
    state_payload = runtime.load_state()

    assert run_status_payload["status"] == "stalled"
    assert run_status_payload["last_error"] == "no_heartbeat_progress"
    assert heartbeat_payload["status"] == "stalled"
    assert state_payload["implement"]["status"] == "stalled"
    assert state_payload["implement"]["metadata"]["stalled_reason"] == "no_heartbeat_progress"
    failure_report = json.loads(Path(outputs["failure_report"]).read_text(encoding="utf-8"))
    assert failure_report["status"] == "stalled"
    assert failure_report["stage"] == "implement"
