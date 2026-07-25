import json
from pathlib import Path

import pytest

from research_agent.inno_common import persist_stage_result
from research_agent.runtime import (
    ArtifactContractError,
    load_stage_artifact,
    load_stage_payload,
    validate_stage_artifacts,
    write_stage_artifact,
)


VALID_ARTIFACTS = {
    ("prepare", "prepare_result.json"): {
        "reference_papers": ["paper"],
        "reference_paths": ["/workplace/reference"],
        "reference_codebases": ["owner/repo"],
    },
    ("survey", "survey_result.json"): {"survey_report": "survey"},
    ("plan", "dataset_plan.json"): {"dataset_description": "dataset"},
    ("plan", "training_plan.json"): {"training_pipeline": "train"},
    ("plan", "testing_plan.json"): {"test_metric": "accuracy"},
    ("plan", "plan_report.json"): {"plan_report": "plan"},
    ("implement", "project_manifest.json"): {
        "implementation_report": "implemented",
        "project_manifest": {
            "project_root": "/workplace/project",
            "exists": True,
            "directories": [],
            "files": ["run_training_testing.py"],
            "key_paths": {"main_script": "/workplace/project/run_training_testing.py"},
        },
    },
    ("judge", "judge_report.json"): {"judge_report": "approved"},
    ("submit", "submit_result.json"): {"submit_result": "metric=1.0"},
    ("analyze", "analysis_report.json"): {"analysis_report": "analysis"},
}


def _artifact_path(root: Path, stage: str, file_name: str) -> Path:
    directory = "plan_stages" if stage == "plan" else f"{stage}_stage"
    return root / directory / file_name


def test_all_real_stage_writes_satisfy_runtime_contracts(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    main_script = project_root / "run_training_testing.py"
    main_script.write_text("print('ok')\n", encoding="utf-8")

    for (stage, file_name), original_payload in VALID_ARTIFACTS.items():
        payload = dict(original_payload)
        if stage == "implement":
            payload["project_manifest"] = {
                **original_payload["project_manifest"],
                "project_root": str(project_root),
                "key_paths": {"main_script": str(main_script)},
            }
        path = _artifact_path(tmp_path, stage, file_name)
        write_stage_artifact(path, stage=stage, payload=payload)

    for stage in ("prepare", "survey", "plan", "implement", "judge", "submit", "analyze"):
        evaluation = validate_stage_artifacts(str(tmp_path), stage)
        assert evaluation["completed"] is True, evaluation


def test_persist_stage_result_writes_versioned_artifact(tmp_path):
    output_path = persist_stage_result(
        str(tmp_path),
        "submit",
        "submit_result.json",
        {"task_id": "task-1", "submit_result": "score=0.9"},
    )

    raw = json.loads(Path(output_path).read_text(encoding="utf-8"))
    artifact = load_stage_artifact(output_path, stage="submit", allow_legacy=False)

    assert raw["schema_version"] == "1"
    assert artifact.task_id == "task-1"
    assert artifact.payload["submit_result"] == "score=0.9"


def test_legacy_implement_and_submit_shapes_are_normalized(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    main_script = project_root / "run_training_testing.py"
    main_script.write_text("print('ok')\n", encoding="utf-8")
    implement_path = _artifact_path(tmp_path, "implement", "project_manifest.json")
    implement_path.parent.mkdir(parents=True)
    implement_path.write_text(
        json.dumps(
            {
                "project_root": str(project_root),
                "exists": True,
                "key_paths": {"main_script": str(main_script)},
            }
        ),
        encoding="utf-8",
    )
    submit_path = _artifact_path(tmp_path, "submit", "submit_result.json")
    submit_path.parent.mkdir(parents=True)
    submit_path.write_text(
        json.dumps({"submission_report": "legacy result"}),
        encoding="utf-8",
    )

    implement = load_stage_payload(implement_path, stage="implement")
    submit = load_stage_payload(submit_path, stage="submit")

    assert implement["project_manifest"]["exists"] is True
    assert submit["submit_result"] == "legacy result"


def test_new_writer_rejects_invalid_payload(tmp_path):
    with pytest.raises(ArtifactContractError):
        write_stage_artifact(
            _artifact_path(tmp_path, "submit", "submit_result.json"),
            stage="submit",
            payload={"submission_report": "old field is not canonical"},
        )
