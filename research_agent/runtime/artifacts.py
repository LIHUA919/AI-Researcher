from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


SCHEMA_VERSION = "1"


class ArtifactContractError(ValueError):
    """Raised when a stage artifact does not satisfy its versioned contract."""


class _PayloadModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PreparePayload(_PayloadModel):
    reference_papers: list[str] = Field(min_length=1)
    reference_paths: list[str] = Field(min_length=1)
    reference_codebases: list[str] = Field(default_factory=list)


class SurveyPayload(_PayloadModel):
    survey_report: str = Field(min_length=1)


class DatasetPlanPayload(_PayloadModel):
    dataset_description: str = Field(min_length=1)


class TrainingPlanPayload(_PayloadModel):
    training_pipeline: str = Field(min_length=1)


class TestingPlanPayload(_PayloadModel):
    test_metric: str = Field(min_length=1)


class PlanReportPayload(_PayloadModel):
    plan_report: str = Field(min_length=1)


class ProjectManifest(_PayloadModel):
    project_root: str = ""
    exists: bool
    directories: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    key_paths: dict[str, str]


class ImplementPayload(_PayloadModel):
    implementation_report: str = ""
    project_manifest: ProjectManifest


class JudgePayload(_PayloadModel):
    judge_report: str = Field(min_length=1)


class SubmitPayload(_PayloadModel):
    submit_result: str = Field(min_length=1)


class AnalyzePayload(_PayloadModel):
    analysis_report: str = Field(min_length=1)


class StageArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = SCHEMA_VERSION
    stage: str
    status: Literal["completed", "failed", "invalid"] = "completed"
    created_at: datetime
    run_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any]


ARTIFACT_PAYLOAD_MODELS: dict[tuple[str, str], type[_PayloadModel]] = {
    ("prepare", "prepare_result.json"): PreparePayload,
    ("survey", "survey_result.json"): SurveyPayload,
    ("plan", "dataset_plan.json"): DatasetPlanPayload,
    ("plan", "training_plan.json"): TrainingPlanPayload,
    ("plan", "testing_plan.json"): TestingPlanPayload,
    ("plan", "plan_report.json"): PlanReportPayload,
    ("implement", "project_manifest.json"): ImplementPayload,
    ("judge", "judge_report.json"): JudgePayload,
    ("submit", "submit_result.json"): SubmitPayload,
    ("analyze", "analysis_report.json"): AnalyzePayload,
}


def _legacy_payload(stage: str, artifact_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    if stage == "implement" and artifact_name == "project_manifest.json":
        if "project_manifest" not in normalized and (
            "exists" in normalized or "key_paths" in normalized
        ):
            manifest_keys = {"project_root", "exists", "directories", "files", "key_paths"}
            manifest = {key: normalized.pop(key) for key in list(normalized) if key in manifest_keys}
            normalized["project_manifest"] = manifest
    if stage == "submit" and artifact_name == "submit_result.json":
        if "submit_result" not in normalized and "submission_report" in normalized:
            normalized["submit_result"] = normalized.pop("submission_report")
    return normalized


def validate_stage_payload(
    stage: str,
    artifact_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    model_type = ARTIFACT_PAYLOAD_MODELS.get((stage, artifact_name))
    if model_type is None:
        raise ArtifactContractError(f"unknown artifact contract: {stage}/{artifact_name}")
    try:
        return model_type.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise ArtifactContractError(str(exc)) from exc


def write_stage_artifact(
    path: str | Path,
    *,
    stage: str,
    payload: dict[str, Any],
    run_id: str | None = None,
    task_id: str | None = None,
    status: Literal["completed", "failed", "invalid"] = "completed",
) -> str:
    output_path = Path(path)
    normalized = validate_stage_payload(stage, output_path.name, payload)
    resolved_task_id = task_id or normalized.get("task_id")
    artifact = StageArtifact(
        stage=stage,
        status=status,
        created_at=datetime.now(timezone.utc),
        run_id=run_id,
        task_id=str(resolved_task_id) if resolved_task_id is not None else None,
        payload=normalized,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


def load_stage_artifact(
    path: str | Path,
    *,
    stage: str,
    allow_legacy: bool = True,
) -> StageArtifact:
    artifact_path = Path(path)
    try:
        raw = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactContractError(f"cannot read artifact: {artifact_path}") from exc
    if not isinstance(raw, dict):
        raise ArtifactContractError(f"artifact must be a JSON object: {artifact_path}")

    if "schema_version" in raw:
        try:
            artifact = StageArtifact.model_validate(raw)
        except ValidationError as exc:
            raise ArtifactContractError(str(exc)) from exc
        if artifact.stage != stage:
            raise ArtifactContractError(
                f"artifact stage mismatch: expected {stage}, found {artifact.stage}"
            )
        payload = artifact.payload
    elif allow_legacy:
        payload = _legacy_payload(stage, artifact_path.name, raw)
        artifact = StageArtifact(
            stage=stage,
            created_at=datetime.fromtimestamp(artifact_path.stat().st_mtime, timezone.utc),
            task_id=str(payload["task_id"]) if payload.get("task_id") is not None else None,
            payload=payload,
        )
    else:
        raise ArtifactContractError(f"legacy artifact is not allowed: {artifact_path}")

    normalized = validate_stage_payload(stage, artifact_path.name, payload)
    return artifact.model_copy(update={"payload": normalized})


def load_stage_payload(
    path: str | Path,
    *,
    stage: str,
    allow_legacy: bool = True,
) -> dict[str, Any]:
    return load_stage_artifact(path, stage=stage, allow_legacy=allow_legacy).payload
