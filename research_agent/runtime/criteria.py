from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict


DEFAULT_STAGE_ORDER = [
    "prepare",
    "survey",
    "plan",
    "implement",
    "judge",
    "submit",
    "analyze",
]


@dataclass(frozen=True)
class StageCriteria:
    stage_name: str
    required_artifacts: tuple[str, ...]


DEFAULT_CRITERIA: dict[str, StageCriteria] = {
    "prepare": StageCriteria(
        stage_name="prepare",
        required_artifacts=("prepare_stage/prepare_result.json",),
    ),
    "survey": StageCriteria(
        stage_name="survey",
        required_artifacts=("survey_stage/survey_result.json",),
    ),
    "plan": StageCriteria(
        stage_name="plan",
        required_artifacts=(
            "plan_stages/dataset_plan.json",
            "plan_stages/training_plan.json",
            "plan_stages/testing_plan.json",
            "plan_stages/plan_report.json",
        ),
    ),
    "implement": StageCriteria(
        stage_name="implement",
        required_artifacts=("implement_stage/project_manifest.json",),
    ),
    "judge": StageCriteria(
        stage_name="judge",
        required_artifacts=("judge_stage/judge_report.json",),
    ),
    "submit": StageCriteria(
        stage_name="submit",
        required_artifacts=("submit_stage/submit_result.json",),
    ),
    "analyze": StageCriteria(
        stage_name="analyze",
        required_artifacts=("analyze_stage/analysis_report.json",),
    ),
}


def _artifact_map(cache_path: str, criteria: StageCriteria) -> Dict[str, str]:
    root = Path(cache_path)
    return {
        Path(rel_path).name: str(root / rel_path)
        for rel_path in criteria.required_artifacts
    }


def validate_stage_artifacts(
    cache_path: str,
    stage_name: str,
    criteria_map: dict[str, StageCriteria] | None = None,
) -> dict:
    criteria_map = criteria_map or DEFAULT_CRITERIA
    criteria = criteria_map.get(stage_name)
    if criteria is None:
        return {
            "stage_name": stage_name,
            "completed": False,
            "missing_artifacts": [],
            "artifacts": {},
        }

    artifacts = _artifact_map(cache_path, criteria)
    missing = [name for name, path in artifacts.items() if not Path(path).exists()]
    return {
        "stage_name": stage_name,
        "completed": not missing,
        "missing_artifacts": missing,
        "artifacts": artifacts,
    }
