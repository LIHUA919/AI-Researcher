import json
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
