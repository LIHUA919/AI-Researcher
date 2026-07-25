from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"


class ArtifactRef(ImmutableModel):
    path: str
    sha256: str = Field(min_length=64, max_length=64)
    media_type: str = "application/octet-stream"
    size_bytes: int = Field(ge=0)


class Hypothesis(ImmutableModel):
    hypothesis_id: str
    task_id: str
    statement: str
    mechanism: str
    expected_metric: str
    metric_direction: Literal["maximize", "minimize"]
    conditions: list[str] = Field(default_factory=list)
    parent_experience_ids: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ExperimentAttempt(ImmutableModel):
    attempt_id: str
    run_id: str
    iteration_id: str
    task_id: str
    hypothesis_id: str
    code_revision: str
    dataset_id: str
    dataset_digest: str
    model_config_digest: str
    seed: int
    budget: dict[str, float | int]
    evaluation_contract_id: str
    recall_snapshot_id: str
    status: Literal["pending", "completed", "failed", "invalid", "cancelled"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)


class Observation(ImmutableModel):
    observation_id: str
    attempt_id: str
    exit_code: int
    metrics: dict[str, float]
    artifact_refs: list[ArtifactRef]
    started_at: datetime
    completed_at: datetime
    environment_fingerprint: str
    error: dict[str, Any] | None = None


class VerificationRecord(ImmutableModel):
    verification_id: str
    observation_id: str
    contract_id: str
    contract_version: str
    evaluator_digest: str
    valid: bool
    passed: bool
    outcome: Literal["positive", "neutral", "negative", "invalid"]
    verified_metrics: dict[str, float]
    baseline_comparison: dict[str, float | str]
    violations: list[str] = Field(default_factory=list)
    evidence_refs: list[ArtifactRef] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ExperienceRecord(ImmutableModel):
    experience_id: str
    task_id: str
    hypothesis: Hypothesis
    attempt: ExperimentAttempt
    observation: Observation
    verification: VerificationRecord | None = None
    analysis: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class KnowledgeRecord(ImmutableModel):
    knowledge_id: str
    task_id: str
    domain: str
    dataset_id: str
    model_family: str
    lesson: str
    conditions: list[str]
    outcome: Literal["positive", "negative"]
    confidence: float = Field(ge=0.0, le=1.0)
    source_experience_ids: list[str] = Field(min_length=1)
    promotion_policy_version: str
    supersedes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ExperienceQuery(ImmutableModel):
    task_id: str | None = None
    outcome: Literal["positive", "neutral", "negative", "invalid"] | None = None
    valid_only: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
