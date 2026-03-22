"""Benchmark runner for goal-driven research evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from research_agent.inno.evals.evaluator import (
    GoalDrivenEvalReport,
    GoalDrivenEvaluator,
)
from research_agent.inno.evals.trace import ResearchRunTrace


@dataclass(slots=True)
class BenchmarkTask:
    """A benchmark task with explicit success conditions."""

    task_id: str
    query: str
    goal: str
    metadata: Dict[str, object] = field(default_factory=dict)


class BenchmarkRunner:
    """Run benchmark tasks and evaluate each run against explicit criteria."""

    def __init__(
        self,
        evaluator: GoalDrivenEvaluator,
        run_fn: Callable[[BenchmarkTask], ResearchRunTrace],
    ) -> None:
        self.evaluator = evaluator
        self.run_fn = run_fn

    def run_task(self, task: BenchmarkTask) -> GoalDrivenEvalReport:
        trace = self.run_fn(task)
        if not trace.goal:
            trace.goal = task.goal
        return self.evaluator.evaluate(trace)

    def run_many(self, tasks: List[BenchmarkTask]) -> List[GoalDrivenEvalReport]:
        return [self.run_task(task) for task in tasks]
