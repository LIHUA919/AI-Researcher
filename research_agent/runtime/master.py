from __future__ import annotations

from dataclasses import dataclass

from research_agent.inno_common import load_stage_state, update_stage_state
from research_agent.runtime.criteria import (
    DEFAULT_CRITERIA,
    DEFAULT_STAGE_ORDER,
    StageCriteria,
    validate_stage_artifacts,
)


@dataclass(frozen=True)
class GoalEvaluation:
    current_stage: str | None
    completed_stages: list[str]
    incomplete_stages: list[str]
    all_criteria_met: bool


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
