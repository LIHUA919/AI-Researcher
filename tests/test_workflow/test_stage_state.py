import json
from pathlib import Path

from research_agent.inno_common import (
    build_project_manifest,
    load_cached_plan_result,
    load_cached_stage_result,
    load_cached_survey_result,
    load_stage_state,
    persist_stage_result,
    persist_survey_result,
    update_stage_state,
)


def test_update_stage_state_persists_status_and_artifacts(tmp_path):
    cache_path = str(tmp_path)

    update_stage_state(
        cache_path,
        "survey",
        "completed",
        artifacts={"survey_result": "survey_stage/survey_result.json"},
        metadata={"source": "cache"},
    )

    payload = load_stage_state(cache_path)

    assert payload["survey"]["status"] == "completed"
    assert payload["survey"]["artifacts"]["survey_result"] == "survey_stage/survey_result.json"
    assert payload["survey"]["metadata"]["source"] == "cache"


def test_load_cached_survey_result_reads_persisted_payload(tmp_path):
    cache_path = str(tmp_path)
    persist_survey_result(cache_path, "task-1", "query", "survey body")

    payload = load_cached_survey_result(cache_path)

    assert payload["task_id"] == "task-1"
    assert payload["survey_report"] == "survey body"


def test_load_cached_plan_result_reads_plan_bundle(tmp_path):
    plan_stage = Path(tmp_path) / "plan_stages"
    plan_stage.mkdir()
    dataset_path = plan_stage / "dataset_plan.json"
    training_path = plan_stage / "training_plan.json"
    testing_path = plan_stage / "testing_plan.json"
    plan_index_path = plan_stage / "plan_index.json"
    plan_report_path = plan_stage / "plan_report.json"

    dataset_path.write_text(json.dumps({"dataset_description": "CIFAR-10"}), encoding="utf-8")
    training_path.write_text(json.dumps({"training_pipeline": "train"}), encoding="utf-8")
    testing_path.write_text(json.dumps({"test_metric": "fid"}), encoding="utf-8")
    plan_index_path.write_text(
        json.dumps(
            {
                "dataset_plan": str(dataset_path),
                "training_plan": str(training_path),
                "testing_plan": str(testing_path),
            }
        ),
        encoding="utf-8",
    )
    plan_report_path.write_text(
        json.dumps({"plan_report": "report body", "task_id": "task-1"}),
        encoding="utf-8",
    )

    payload = load_cached_plan_result(str(tmp_path))

    assert payload["plan_report"] == "report body"
    assert payload["dataset_plan"]["dataset_description"] == "CIFAR-10"
    assert payload["training_plan"]["training_pipeline"] == "train"
    assert payload["testing_plan"]["test_metric"] == "fid"


def test_persist_stage_result_round_trips_payload(tmp_path):
    output_path = persist_stage_result(
        str(tmp_path),
        "judge",
        "judge_report.json",
        {"judge_report": "looks good"},
    )

    payload = load_cached_stage_result(str(tmp_path), "judge", "judge_report.json")

    assert output_path.endswith("judge_stage/judge_report.json")
    assert payload["judge_report"] == "looks good"


def test_build_project_manifest_lists_project_contents(tmp_path):
    project_dir = tmp_path / "workplace" / "project"
    (project_dir / "model").mkdir(parents=True)
    (project_dir / "training").mkdir()
    run_script = project_dir / "run_training_testing.py"
    run_script.write_text("print('ok')", encoding="utf-8")

    manifest = build_project_manifest(str(tmp_path), "workplace")

    assert manifest["exists"] is True
    assert "model" in manifest["directories"]
    assert "run_training_testing.py" in manifest["files"]
    assert manifest["key_paths"]["main_script"].endswith("project/run_training_testing.py")
