from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Dict


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
class GuardrailResult:
    passed: bool
    violations: tuple[str, ...] = ()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _validate_prepare_guardrail(cache_path: str) -> GuardrailResult:
    payload = _read_json(Path(cache_path) / "prepare_stage" / "prepare_result.json")
    violations: list[str] = []
    if not payload.get("reference_papers"):
        violations.append("missing_reference_papers")
    if not payload.get("reference_paths"):
        violations.append("missing_reference_paths")
    return GuardrailResult(not violations, tuple(violations))


def _validate_survey_guardrail(cache_path: str) -> GuardrailResult:
    payload = _read_json(Path(cache_path) / "survey_stage" / "survey_result.json")
    if payload.get("survey_report"):
        return GuardrailResult(True)
    return GuardrailResult(False, ("missing_survey_report",))


def _validate_plan_guardrail(cache_path: str) -> GuardrailResult:
    root = Path(cache_path) / "plan_stages"
    dataset_plan = _read_json(root / "dataset_plan.json")
    training_plan = _read_json(root / "training_plan.json")
    testing_plan = _read_json(root / "testing_plan.json")
    plan_report = _read_json(root / "plan_report.json")
    violations: list[str] = []
    if not dataset_plan.get("dataset_description"):
        violations.append("missing_dataset_description")
    if not training_plan.get("training_pipeline"):
        violations.append("missing_training_pipeline")
    if not testing_plan.get("test_metric"):
        violations.append("missing_test_metric")
    if not plan_report.get("plan_report"):
        violations.append("missing_plan_report")
    return GuardrailResult(not violations, tuple(violations))


def _validate_implement_guardrail(cache_path: str) -> GuardrailResult:
    payload = _read_json(Path(cache_path) / "implement_stage" / "project_manifest.json")
    violations: list[str] = []
    if not payload.get("exists"):
        violations.append("project_missing")
    key_paths = payload.get("key_paths") or {}
    if not key_paths.get("main_script"):
        violations.append("missing_main_script_path")
    return GuardrailResult(not violations, tuple(violations))


def _validate_named_report_guardrail(
    cache_path: str,
    rel_path: str,
    key: str,
    violation: str,
) -> GuardrailResult:
    payload = _read_json(Path(cache_path) / rel_path)
    if payload.get(key):
        return GuardrailResult(True)
    return GuardrailResult(False, (violation,))


@dataclass(frozen=True)
class StageCriteria:
    stage_name: str
    required_artifacts: tuple[str, ...]
    guardrail: Callable[[str], GuardrailResult] | None = None


DEFAULT_CRITERIA: dict[str, StageCriteria] = {
    "prepare": StageCriteria(
        stage_name="prepare",
        required_artifacts=("prepare_stage/prepare_result.json",),
        guardrail=_validate_prepare_guardrail,
    ),
    "survey": StageCriteria(
        stage_name="survey",
        required_artifacts=("survey_stage/survey_result.json",),
        guardrail=_validate_survey_guardrail,
    ),
    "plan": StageCriteria(
        stage_name="plan",
        required_artifacts=(
            "plan_stages/dataset_plan.json",
            "plan_stages/training_plan.json",
            "plan_stages/testing_plan.json",
            "plan_stages/plan_report.json",
        ),
        guardrail=_validate_plan_guardrail,
    ),
    "implement": StageCriteria(
        stage_name="implement",
        required_artifacts=("implement_stage/project_manifest.json",),
        guardrail=_validate_implement_guardrail,
    ),
    "judge": StageCriteria(
        stage_name="judge",
        required_artifacts=("judge_stage/judge_report.json",),
        guardrail=lambda cache_path: _validate_named_report_guardrail(
            cache_path, "judge_stage/judge_report.json", "judge_report", "missing_judge_report"
        ),
    ),
    "submit": StageCriteria(
        stage_name="submit",
        required_artifacts=("submit_stage/submit_result.json",),
        guardrail=lambda cache_path: _validate_named_report_guardrail(
            cache_path, "submit_stage/submit_result.json", "submit_result", "missing_submit_result"
        ),
    ),
    "analyze": StageCriteria(
        stage_name="analyze",
        required_artifacts=("analyze_stage/analysis_report.json",),
        guardrail=lambda cache_path: _validate_named_report_guardrail(
            cache_path, "analyze_stage/analysis_report.json", "analysis_report", "missing_analysis_report"
        ),
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
    guardrail_result = GuardrailResult(True)
    if not missing and criteria.guardrail is not None:
        guardrail_result = criteria.guardrail(cache_path)
    return {
        "stage_name": stage_name,
        "completed": not missing and guardrail_result.passed,
        "missing_artifacts": missing,
        "artifacts": artifacts,
        "guardrail_passed": guardrail_result.passed,
        "guardrail_violations": list(guardrail_result.violations),
    }
