from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from research_agent.inno_common import load_stage_state, update_stage_state
from research_agent.runtime.criteria import (
    DEFAULT_CRITERIA,
    DEFAULT_STAGE_ORDER,
    StageCriteria,
    validate_stage_artifacts,
)
from research_agent.runtime.heartbeat import (
    parse_runtime_timestamp,
    read_runtime_json,
    write_heartbeat,
    write_run_status,
)


@dataclass(frozen=True)
class GoalEvaluation:
    current_stage: str | None
    completed_stages: list[str]
    incomplete_stages: list[str]
    all_criteria_met: bool


@dataclass(frozen=True)
class StallEvaluation:
    stalled: bool
    current_stage: str | None
    age_seconds: float | None
    reason: str


class MasterRuntime:
    def __init__(
        self,
        cache_path: str,
        criteria_map: dict[str, StageCriteria] | None = None,
        stage_order: list[str] | None = None,
    ):
        self.cache_path = cache_path
        self.criteria_map = criteria_map or DEFAULT_CRITERIA
        self.stage_order = stage_order or DEFAULT_STAGE_ORDER

    def load_state(self) -> dict:
        return load_stage_state(self.cache_path)

    def load_heartbeat(self) -> dict:
        return read_runtime_json(self.cache_path, "heartbeat.json")

    def load_run_status(self) -> dict:
        return read_runtime_json(self.cache_path, "run_status.json")

    def latest_artifact(self) -> str | None:
        state = self.load_state()
        for stage_name in reversed(self.stage_order):
            stage_state = state.get(stage_name, {})
            artifacts = stage_state.get("artifacts") or {}
            for artifact_path in artifacts.values():
                if artifact_path:
                    return artifact_path
        return None

    def stage_index(self, stage_name: str) -> int:
        return self.stage_order.index(stage_name)

    def evaluate_stage(self, stage_name: str) -> dict:
        return validate_stage_artifacts(self.cache_path, stage_name, self.criteria_map)

    def sync_stage_state(self) -> dict:
        state = self.load_state()
        for stage_name in self.stage_order:
            evaluation = self.evaluate_stage(stage_name)
            if evaluation["completed"]:
                update_stage_state(
                    self.cache_path,
                    stage_name,
                    "completed",
                    artifacts=evaluation["artifacts"],
                    metadata=state.get(stage_name, {}).get("metadata", {}),
                )
        return self.load_state()

    def evaluate_goal(self) -> GoalEvaluation:
        completed_stages: list[str] = []
        incomplete_stages: list[str] = []
        for stage_name in self.stage_order:
            evaluation = self.evaluate_stage(stage_name)
            if evaluation["completed"]:
                completed_stages.append(stage_name)
            else:
                incomplete_stages.append(stage_name)

        return GoalEvaluation(
            current_stage=incomplete_stages[0] if incomplete_stages else None,
            completed_stages=completed_stages,
            incomplete_stages=incomplete_stages,
            all_criteria_met=not incomplete_stages,
        )

    def next_stage(self) -> str | None:
        return self.evaluate_goal().current_stage

    def can_run_stage(self, stage_name: str) -> bool:
        if stage_name not in self.stage_order:
            return False
        stage_index = self.stage_index(stage_name)
        required_stages = self.stage_order[:stage_index]
        return all(self.evaluate_stage(required_stage)["completed"] for required_stage in required_stages)

    def should_run_stage(self, stage_name: str) -> bool:
        evaluation = self.evaluate_stage(stage_name)
        return not evaluation["completed"]

    def record_stage_completion(
        self,
        stage_name: str,
        artifacts: dict[str, str] | None = None,
        metadata: dict | None = None,
    ) -> dict:
        update_stage_state(
            self.cache_path,
            stage_name,
            "completed",
            artifacts=artifacts or {},
            metadata=metadata or {},
        )
        return self.sync_stage_state()

    def record_stage_failure(
        self,
        stage_name: str,
        error_message: str,
        metadata: dict | None = None,
    ) -> dict:
        state = self.load_state()
        stage_state = state.get(stage_name, {})
        merged_metadata = dict(stage_state.get("metadata", {}))
        merged_metadata.update(metadata or {})
        merged_metadata["last_error"] = error_message
        update_stage_state(
            self.cache_path,
            stage_name,
            "failed",
            artifacts=stage_state.get("artifacts", {}),
            metadata=merged_metadata,
        )
        return self.load_state()

    def write_runtime_status(
        self,
        *,
        run_id: str,
        status: str,
        last_error: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, str]:
        goal = self.evaluate_goal()
        current_stage = goal.current_stage
        heartbeat_path = write_heartbeat(
            self.cache_path,
            current_stage=current_stage,
            status=status,
            last_error=last_error,
            metadata=metadata,
        )
        run_status_path = write_run_status(
            self.cache_path,
            run_id=run_id,
            status=status,
            current_stage=current_stage,
            completed_stages=goal.completed_stages,
            incomplete_stages=goal.incomplete_stages,
            latest_artifact=self.latest_artifact(),
            last_error=last_error,
        )
        return {
            "heartbeat": heartbeat_path,
            "run_status": run_status_path,
        }

    def write_failure_status(
        self,
        *,
        run_id: str,
        error_message: str,
        stage_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, str]:
        if stage_name:
            self.record_stage_failure(stage_name, error_message, metadata=metadata)
        return self.write_runtime_status(
            run_id=run_id,
            status="failed",
            last_error=error_message,
            metadata=metadata,
        )

    def evaluate_stall(
        self,
        *,
        max_stale_seconds: int,
        now: datetime | None = None,
    ) -> StallEvaluation:
        heartbeat = self.load_heartbeat()
        if not heartbeat:
            return StallEvaluation(False, None, None, "missing_heartbeat")

        status = heartbeat.get("status")
        current_stage = heartbeat.get("current_stage")
        if status != "running":
            return StallEvaluation(False, current_stage, None, f"status_{status or 'unknown'}")

        updated_at = parse_runtime_timestamp(heartbeat.get("updated_at"))
        if updated_at is None:
            return StallEvaluation(False, current_stage, None, "invalid_timestamp")

        effective_now = now or datetime.now(timezone.utc)
        age_seconds = max((effective_now - updated_at).total_seconds(), 0.0)
        if age_seconds > max_stale_seconds:
            return StallEvaluation(True, current_stage, age_seconds, "heartbeat_stale")

        return StallEvaluation(False, current_stage, age_seconds, "healthy")

    def write_stalled_status(
        self,
        *,
        run_id: str,
        reason: str,
        stage_name: str | None = None,
        metadata: dict | None = None,
    ) -> dict[str, str]:
        if stage_name:
            state = self.load_state()
            stage_state = state.get(stage_name, {})
            merged_metadata = dict(stage_state.get("metadata", {}))
            merged_metadata.update(metadata or {})
            merged_metadata["stalled_reason"] = reason
            update_stage_state(
                self.cache_path,
                stage_name,
                "stalled",
                artifacts=stage_state.get("artifacts", {}),
                metadata=merged_metadata,
            )
        return self.write_runtime_status(
            run_id=run_id,
            status="stalled",
            last_error=reason,
            metadata=metadata,
        )
