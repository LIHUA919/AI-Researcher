from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from research_agent.inno.experience import LoopOutcome, RecallContext
from research_agent.runtime.adaptive_experiment import PreviousAttemptFeedback
from research_agent.runtime.experience_adapter import ExperienceRunAdapter


@dataclass(frozen=True)
class ImprovementCycleRequest:
    run_id: str
    task_id: str
    query: str
    model: str
    domain: str
    dataset_id: str
    model_family: str
    project_dir: str | Path
    run_cache_path: str | Path
    seed: int = 0


@dataclass(frozen=True)
class ImprovementAttemptContext:
    iteration_number: int
    attempt_cache_path: Path
    recall_context: RecallContext | None
    previous_feedback: PreviousAttemptFeedback | None
    verification_check: Callable[[], bool] | None


@dataclass(frozen=True)
class ImprovementCycleResult:
    flow_result: dict
    outcome: LoopOutcome | None
    recall_context: RecallContext | None
    iteration_number: int
    attempt_cache_path: Path


AttemptRunner = Callable[[ImprovementAttemptContext], dict]


def _merge_llm_usage(total: dict, usage: dict) -> None:
    for field in ("calls", "prompt_tokens", "completion_tokens", "total_tokens"):
        total[field] = int(total.get(field, 0) or 0) + int(usage.get(field, 0) or 0)
    total_models = total.setdefault("by_model", {})
    for model, model_usage in (usage.get("by_model") or {}).items():
        target = total_models.setdefault(model, {})
        for field in ("calls", "prompt_tokens", "completion_tokens", "total_tokens"):
            target[field] = int(target.get(field, 0) or 0) + int(
                model_usage.get(field, 0) or 0
            )


class ImprovementCycleRunner:
    """Run, verify, recall, and retry isolated Experiment Attempts."""

    def __init__(self, experience: ExperienceRunAdapter) -> None:
        self.experience = experience

    def run(
        self,
        request: ImprovementCycleRequest,
        run_attempt: AttemptRunner,
    ) -> ImprovementCycleResult:
        recall_context = self.experience.before_run(
            task_id=request.task_id,
            query=request.query,
            domain=request.domain,
            dataset_id=request.dataset_id,
            model_family=request.model_family,
        )
        outcome = None
        flow_result = None
        attempt_context = None
        previous_feedback: PreviousAttemptFeedback | None = None
        cycle_llm_usage: dict = {}
        attempt_llm_usage: list[dict] = []
        iteration_limit = (
            self.experience.max_iterations
            if self.experience.runs_closed_loop
            else 1
        )

        for iteration_number in range(1, iteration_limit + 1):
            attempt_context = ImprovementAttemptContext(
                iteration_number=iteration_number,
                attempt_cache_path=self._attempt_cache_path(
                    request.run_cache_path,
                    iteration_number,
                ),
                recall_context=recall_context,
                previous_feedback=previous_feedback,
                verification_check=self.experience.pending_verification_check(),
            )
            attempt_context.attempt_cache_path.mkdir(parents=True, exist_ok=True)
            attempt_recorded = False
            try:
                flow_result = run_attempt(attempt_context)
                usage = (flow_result.get("metadata") or {}).get("llm_usage") or {}
                if usage:
                    _merge_llm_usage(cycle_llm_usage, usage)
                    attempt_llm_usage.append(
                        {
                            "iteration_number": iteration_number,
                            "usage": copy.deepcopy(usage),
                        }
                    )
                outcome = self.experience.after_flow(
                    flow_result,
                    project_dir=request.project_dir,
                    run_id=request.run_id,
                    model=request.model,
                    domain=request.domain,
                    dataset_id=request.dataset_id,
                    model_family=request.model_family,
                    recall_context=recall_context,
                    iteration_number=iteration_number,
                    seed=request.seed,
                )
                previous_feedback = self.experience.build_previous_feedback(
                    flow_result,
                    outcome,
                )
                attempt_recorded = self.experience.records_experience
                self.experience.finalize_runtime(
                    run_id=request.run_id,
                    outcome=outcome,
                )
            except Exception as exc:
                failed_outcome = None
                if self.experience.records_experience and not attempt_recorded:
                    failed_outcome = self.experience.after_failure(
                        project_dir=request.project_dir,
                        run_id=request.run_id,
                        task_id=request.task_id,
                        query=request.query,
                        model=request.model,
                        domain=request.domain,
                        dataset_id=request.dataset_id,
                        model_family=request.model_family,
                        recall_context=recall_context,
                        iteration_number=iteration_number,
                        seed=request.seed,
                        error=exc,
                    )
                    self.experience.finalize_runtime(
                        run_id=request.run_id,
                        outcome=failed_outcome,
                    )
                outcome = failed_outcome
                if (
                    not self.experience.runs_closed_loop
                    or failed_outcome is None
                    or failed_outcome.action != "continue"
                    or iteration_number >= iteration_limit
                ):
                    raise
                recall_context = self.experience.before_run(
                    task_id=request.task_id,
                    query=request.query,
                    domain=request.domain,
                    dataset_id=request.dataset_id,
                    model_family=request.model_family,
                )
                continue

            if (
                not self.experience.runs_closed_loop
                or outcome is None
                or outcome.action != "continue"
            ):
                break
            recall_context = self.experience.before_run(
                task_id=request.task_id,
                query=request.query,
                domain=request.domain,
                dataset_id=request.dataset_id,
                model_family=request.model_family,
            )

        if flow_result is None or attempt_context is None:
            raise RuntimeError("improvement cycle completed without an Experiment Attempt")
        if cycle_llm_usage:
            flow_result = dict(flow_result)
            metadata = dict(flow_result.get("metadata") or {})
            metadata["llm_usage"] = cycle_llm_usage
            metadata["attempt_llm_usage"] = attempt_llm_usage
            flow_result["metadata"] = metadata
        return ImprovementCycleResult(
            flow_result=flow_result,
            outcome=outcome,
            recall_context=recall_context,
            iteration_number=attempt_context.iteration_number,
            attempt_cache_path=attempt_context.attempt_cache_path,
        )

    def _attempt_cache_path(
        self,
        run_cache_path: str | Path,
        iteration_number: int,
    ) -> Path:
        root = Path(run_cache_path)
        adaptive = bool(
            getattr(self.experience, "contract", None) is not None
            and self.experience.contract.adaptive_experiment is not None
        )
        if not self.experience.runs_closed_loop and not adaptive:
            return root
        return root / "attempts" / f"iteration-{iteration_number:03d}"
