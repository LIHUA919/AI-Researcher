from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import fmean, pvariance
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field


class BenchmarkConfigurationError(ValueError):
    """Raised when an Experience Gain comparison is not paired and comparable."""


class ExperienceBenchmarkTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    query: str
    goal: str
    primary_metric: str
    direction: Literal["maximize", "minimize"] = "maximize"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrialConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    mode: Literal["off", "closed-loop"]
    seed: int
    model: str
    budget: dict[str, float | int]
    evaluator_version: str
    dataset_digest: str
    code_revision: str


class TrialResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float
    valid: bool = True
    tokens: int = Field(default=0, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0)
    gpu_hours: float = Field(default=0.0, ge=0)
    failure_signature: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)


class ModeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["off", "closed-loop"]
    scores: list[float]
    mean: float
    variance: float
    valid_rate: float
    repeated_failure_rate: float
    total_tokens: int
    total_wall_seconds: float
    total_gpu_hours: float


class ExperienceGainReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    task: ExperienceBenchmarkTask
    seeds: list[int]
    model: str
    budget: dict[str, float | int]
    evaluator_version: str
    dataset_digest: str
    code_revision: str
    baseline: ModeSummary
    closed_loop: ModeSummary
    paired_deltas: list[float]
    experience_gain: float
    generated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


TrialFn = Callable[[TrialConfiguration], TrialResult]


class ExperienceBenchmarkRunner:
    def __init__(self, trial_fn: TrialFn) -> None:
        self.trial_fn = trial_fn

    def run(
        self,
        task: ExperienceBenchmarkTask,
        *,
        seeds: list[int],
        model: str,
        budget: dict[str, float | int],
        evaluator_version: str,
        dataset_digest: str,
        code_revision: str,
        metadata: dict[str, Any] | None = None,
    ) -> ExperienceGainReport:
        if not seeds or len(seeds) != len(set(seeds)):
            raise BenchmarkConfigurationError("seeds must be non-empty and unique")
        results: dict[str, list[TrialResult]] = {"off": [], "closed-loop": []}
        for seed in seeds:
            for mode in ("off", "closed-loop"):
                config = TrialConfiguration(
                    task_id=task.task_id,
                    mode=mode,
                    seed=seed,
                    model=model,
                    budget=budget,
                    evaluator_version=evaluator_version,
                    dataset_digest=dataset_digest,
                    code_revision=code_revision,
                )
                results[mode].append(self.trial_fn(config))

        baseline = self._summary("off", results["off"])
        closed_loop = self._summary("closed-loop", results["closed-loop"])
        paired_deltas = [
            round(
                self._improvement(
                    task.direction,
                    baseline_result.score,
                    closed_result.score,
                ),
                12,
            )
            for baseline_result, closed_result in zip(
                results["off"],
                results["closed-loop"],
                strict=True,
            )
        ]
        return ExperienceGainReport(
            task=task,
            seeds=seeds,
            model=model,
            budget=budget,
            evaluator_version=evaluator_version,
            dataset_digest=dataset_digest,
            code_revision=code_revision,
            baseline=baseline,
            closed_loop=closed_loop,
            paired_deltas=paired_deltas,
            experience_gain=round(fmean(paired_deltas), 12),
            generated_at=datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _improvement(
        direction: Literal["maximize", "minimize"],
        baseline: float,
        closed_loop: float,
    ) -> float:
        return (
            closed_loop - baseline
            if direction == "maximize"
            else baseline - closed_loop
        )

    @staticmethod
    def _summary(
        mode: Literal["off", "closed-loop"],
        results: list[TrialResult],
    ) -> ModeSummary:
        scores = [result.score for result in results]
        failures = [
            result.failure_signature
            for result in results
            if result.failure_signature is not None
        ]
        repeated_failures = len(failures) - len(set(failures))
        return ModeSummary(
            mode=mode,
            scores=scores,
            mean=round(fmean(scores), 12),
            variance=round(pvariance(scores), 12),
            valid_rate=round(sum(result.valid for result in results) / len(results), 12),
            repeated_failure_rate=round(repeated_failures / len(results), 12),
            total_tokens=sum(result.tokens for result in results),
            total_wall_seconds=sum(result.wall_seconds for result in results),
            total_gpu_hours=sum(result.gpu_hours for result in results),
        )


def save_experience_gain_report(
    report: ExperienceGainReport,
    path: str | Path,
) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


def load_scientist_bench_task(
    path: str | Path,
    *,
    task_level: str,
    primary_metric: str,
    direction: Literal["maximize", "minimize"] = "maximize",
) -> ExperienceBenchmarkTask:
    source_path = Path(path)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    return ExperienceBenchmarkTask(
        task_id=f"{payload['instance_id']}:{task_level}",
        query=payload[task_level],
        goal=payload.get("target") or payload.get("abstract", ""),
        primary_metric=primary_metric,
        direction=direction,
        metadata={
            "source_path": str(source_path),
            "instance_id": payload["instance_id"],
            "year": payload.get("year"),
        },
    )
