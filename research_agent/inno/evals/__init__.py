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
    StructuralEvaluator,
    build_default_research_evaluator,
)
from research_agent.inno.evals.metrics import evidence_coverage, plan_executability
from research_agent.inno.evals.trace import (
    AgentStepTrace,
    ResearchRunTrace,
    RetrievalItem,
    ToolCallTrace,
)
from research_agent.inno.evals.experience_benchmark import (
    BenchmarkConfigurationError,
    ExperienceBenchmarkRunner,
    ExperienceBenchmarkTask,
    ExperienceGainReport,
    ModeSummary,
    TrialConfiguration,
    TrialPair,
    TrialResult,
    load_scientist_bench_task,
    save_experience_gain_report,
)
from research_agent.inno.evals.scientist_bench import (
    CandidateGeneration,
    CandidateRequest,
    OpenAICompatibleSolutionGenerator,
    ScientistBenchTrialAdapter,
    SolutionGenerator,
    VerifiedTrialManifest,
)

__all__ = [
    "AgentStepTrace",
    "AsyncBenchmarkRunner",
    "BenchmarkRunner",
    "BenchmarkConfigurationError",
    "BenchmarkTask",
    "CandidateGeneration",
    "CandidateRequest",
    "CriterionScore",
    "EvalCriterion",
    "ExperienceBenchmarkRunner",
    "ExperienceBenchmarkTask",
    "ExperienceGainReport",
    "GoalDrivenEvalReport",
    "GoalDrivenEvaluator",
    "StructuralEvaluator",
    "ResearchRunTrace",
    "ModeSummary",
    "OpenAICompatibleSolutionGenerator",
    "RetrievalItem",
    "ScientistBenchTrialAdapter",
    "SolutionGenerator",
    "ToolCallTrace",
    "TrialConfiguration",
    "TrialPair",
    "TrialResult",
    "VerifiedTrialManifest",
    "build_and_save_eval_result",
    "build_research_run_trace",
    "save_eval_artifacts",
    "build_default_research_evaluator",
    "evidence_coverage",
    "plan_executability",
    "load_scientist_bench_task",
    "save_experience_gain_report",
]
