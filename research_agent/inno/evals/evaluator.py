"""Goal-driven evaluators for research runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from research_agent.inno.evals.metrics import evidence_coverage, plan_executability
from research_agent.inno.evals.trace import ResearchRunTrace


MetricFn = Callable[[ResearchRunTrace], Dict[str, Any]]


@dataclass(slots=True)
class EvalCriterion:
    """A measurable acceptance criterion for a research goal."""

    name: str
    description: str
    threshold: float
    metric_fn: MetricFn


@dataclass(slots=True)
class CriterionScore:
    """Evaluation output for one criterion."""

    name: str
    score: float
    passed: bool
    description: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GoalDrivenEvalReport:
    """Master evaluation report over a run trace."""

    task_id: str
    goal: str
    passed: bool
    criteria_scores: List[CriterionScore]
    failure_reasons: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)


class GoalDrivenEvaluator:
    """Evaluate a run against an explicit goal and criteria.

    This mirrors the goal-driven control loop: define a goal, define concrete
    criteria, then let the evaluator decide whether the run satisfied them.
    """

    def __init__(self, goal: str, criteria: List[EvalCriterion]) -> None:
        self.goal = goal
        self.criteria = criteria

    def evaluate(self, trace: ResearchRunTrace) -> GoalDrivenEvalReport:
        criteria_scores: List[CriterionScore] = []
        failure_reasons: List[str] = []
        next_actions: List[str] = []

        for criterion in self.criteria:
            details = criterion.metric_fn(trace)
            score = float(details.get("score", 0.0))
            passed = score >= criterion.threshold
            criteria_scores.append(
                CriterionScore(
                    name=criterion.name,
                    score=score,
                    passed=passed,
                    description=criterion.description,
                    details=details,
                )
            )
            if not passed:
                failure_reasons.append(
                    f"{criterion.name} below threshold {criterion.threshold:.2f}"
                )
                next_actions.append(self._suggest_next_action(criterion.name, details))

        return GoalDrivenEvalReport(
            task_id=trace.task_id,
            goal=self.goal or trace.goal,
            passed=all(item.passed for item in criteria_scores),
            criteria_scores=criteria_scores,
            failure_reasons=failure_reasons,
            next_actions=[action for action in next_actions if action],
        )

    @staticmethod
    def _suggest_next_action(name: str, details: Mapping[str, Any]) -> str:
        if name == "evidence_coverage":
            unsupported = details.get("unsupported_claims", [])
            return (
                "Add retrieval evidence or reduce unsupported claims: "
                + ", ".join(unsupported[:3])
            ).rstrip(": ")
        if name == "plan_executability":
            missing = details.get("missing_sections", [])
            return "Fill missing plan sections: " + ", ".join(missing)
        return ""


def build_default_research_evaluator(goal: str = "") -> GoalDrivenEvaluator:
    """Build the minimal evaluator for the first eval iteration."""

    criteria = [
        EvalCriterion(
            name="evidence_coverage",
            description="Key claims should be backed by retrieved evidence or tool outputs.",
            threshold=0.7,
            metric_fn=evidence_coverage,
        ),
        EvalCriterion(
            name="plan_executability",
            description="The implementation plan should contain the required executable sections.",
            threshold=0.75,
            metric_fn=lambda trace: plan_executability(trace.plan),
        ),
    ]
    return GoalDrivenEvaluator(goal=goal, criteria=criteria)
