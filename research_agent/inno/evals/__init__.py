"""Goal-driven evaluation primitives for AI-Researcher."""

from research_agent.inno.evals.adapter import (
    build_and_save_eval_result,
    build_research_run_trace,
    save_eval_artifacts,
)
from research_agent.inno.evals.bench_runner import BenchmarkRunner, BenchmarkTask
from research_agent.inno.evals.bench_runner import AsyncBenchmarkRunner
from research_agent.inno.evals.evaluator import (
    CriterionScore,
    EvalCriterion,
    GoalDrivenEvalReport,
    GoalDrivenEvaluator,
    build_default_research_evaluator,
)
from research_agent.inno.evals.metrics import evidence_coverage, plan_executability
from research_agent.inno.evals.trace import (
    AgentStepTrace,
    ResearchRunTrace,
    RetrievalItem,
    ToolCallTrace,
)

__all__ = [
    "AgentStepTrace",
    "AsyncBenchmarkRunner",
    "BenchmarkRunner",
    "BenchmarkTask",
    "CriterionScore",
    "EvalCriterion",
    "GoalDrivenEvalReport",
    "GoalDrivenEvaluator",
    "ResearchRunTrace",
    "RetrievalItem",
    "ToolCallTrace",
    "build_and_save_eval_result",
    "build_research_run_trace",
    "save_eval_artifacts",
    "build_default_research_evaluator",
    "evidence_coverage",
    "plan_executability",
]
