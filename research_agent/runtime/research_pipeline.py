from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from research_agent.inno.experience.models import Hypothesis, RecallContext
from research_agent.runtime.context import RunContext
from research_agent.runtime.hooks import JsonlRuntimeHooks
from research_agent.runtime.master import GoalEvaluation, MasterRuntime


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    task_id: str
    entrypoint: str
    task_level: str
    model: str
    workplace_name: str
    cache_path: str
    instance_path: str | None = None
    intent: str
    expected_metric: str = "primary_metric"
    metric_direction: Literal["maximize", "minimize"] = "maximize"
    conditions: list[str] = Field(default_factory=list)


class ResearchIntentStrategy(Protocol):
    def build_hypothesis(
        self,
        request: RunRequest,
        recall: RecallContext | None = None,
    ) -> Hypothesis: ...


def render_recall_guidance(recall: RecallContext | None) -> str:
    """Render bounded verified experience as cited instructions for a decision."""

    if recall is None or not recall.items:
        return (
            "No verified prior experience was recalled. Evaluate the current "
            "Hypothesis from first principles."
        )
    lessons = "\n".join(
        (
            f"- [{item.citation_id}] outcome={item.outcome}: "
            f"{item.lesson.strip()}"
        )
        for item in recall.items
    )
    return (
        "Verified Recall Context:\n"
        f"{lessons}\n"
        "Use these cited results to revise the current Hypothesis and execution "
        "plan. Do not repeat a verified negative configuration without new "
        "evidence, and preserve the citation IDs in the reasoning."
    )


def _hypothesis(
    request: RunRequest,
    statement: str,
    mechanism: str,
    recall: RecallContext | None,
) -> Hypothesis:
    parent_ids = sorted(
        {
            experience_id
            for item in (recall.items if recall is not None else [])
            for experience_id in item.source_experience_ids
        }
    )
    citations = [
        item.citation_id for item in (recall.items if recall is not None else [])
    ]
    payload = {
        "task_id": request.task_id,
        "statement": statement.strip(),
        "mechanism": mechanism.strip(),
        "expected_metric": request.expected_metric,
        "metric_direction": request.metric_direction,
        "conditions": request.conditions,
        "parent_experience_ids": parent_ids,
        "citations": citations,
    }
    hypothesis_id = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return Hypothesis(hypothesis_id=hypothesis_id, **payload)


class ProvidedIdeaStrategy:
    def build_hypothesis(
        self,
        request: RunRequest,
        recall: RecallContext | None = None,
    ) -> Hypothesis:
        return _hypothesis(
            request,
            request.intent,
            "Implement and independently evaluate the provided research idea.",
            recall,
        )


class ReferenceIdeationStrategy:
    def build_hypothesis(
        self,
        request: RunRequest,
        recall: RecallContext | None = None,
    ) -> Hypothesis:
        return _hypothesis(
            request,
            request.intent,
            "The selected idea synthesizes gaps found in the supplied references.",
            recall,
        )


@dataclass
class ResearchPipeline:
    request: RunRequest
    runtime: MasterRuntime
    run_context: RunContext
    context_variables: dict[str, Any]

    @classmethod
    def start(
        cls,
        request: RunRequest,
        *,
        extra_context: dict[str, Any] | None = None,
        require_verification_for_completion: bool = False,
        verification_check=None,
    ) -> "ResearchPipeline":
        runtime = MasterRuntime(
            request.cache_path,
            hooks=JsonlRuntimeHooks(request.cache_path),
            require_verification_for_completion=require_verification_for_completion,
            verification_check=verification_check,
        )
        runtime.sync_stage_state()
        run_context = RunContext(
            run_id=request.run_id,
            cache_path=request.cache_path,
            entrypoint=request.entrypoint,
            task_level=request.task_level,
            model=request.model,
            workplace_name=request.workplace_name,
            instance_path=request.instance_path,
            metadata={"task_id": request.task_id},
        )
        runtime.write_runtime_status(
            run_id=request.run_id,
            status="running",
            metadata={
                "entrypoint": request.entrypoint,
                "task_level": request.task_level,
            },
        )
        run_context.refresh_stage_state(runtime.load_state())
        context_variables = run_context.to_context_variables(extra=extra_context)
        context_variables["task_id"] = request.task_id
        return cls(
            request=request,
            runtime=runtime,
            run_context=run_context,
            context_variables=context_variables,
        )

    def complete_stage(
        self,
        stage_name: str,
        *,
        artifacts: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        if not self.runtime.can_run_stage(stage_name):
            raise RuntimeError(
                f"Stage '{stage_name}' cannot run before its prerequisites."
            )
        state = self.runtime.record_stage_completion(
            stage_name,
            artifacts=artifacts,
            metadata=metadata,
        )
        stage_state = state.get(stage_name, {})
        if stage_state.get("status") == "failed":
            violations = (stage_state.get("metadata") or {}).get(
                "guardrail_violations",
                [],
            )
            reason = ", ".join(violations) if violations else "unknown_violation"
            raise RuntimeError(
                f"Stage '{stage_name}' rejected by guardrail: {reason}"
            )
        self.run_context.refresh_stage_state(state)
        self.context_variables["stage_state"] = self.run_context.stage_state
        self.context_variables["runtime_context"] = self.run_context.to_payload()
        return state

    def progress(self) -> None:
        self.runtime.write_runtime_status(
            run_id=self.request.run_id,
            status="running",
            metadata={
                "entrypoint": self.request.entrypoint,
                "task_level": self.request.task_level,
            },
        )

    def finalize(self) -> GoalEvaluation:
        self.runtime.sync_stage_state()
        goal = self.runtime.evaluate_goal()
        self.runtime.write_runtime_status(
            run_id=self.request.run_id,
            status="completed" if goal.all_criteria_met else "running",
            metadata={
                "entrypoint": self.request.entrypoint,
                "task_level": self.request.task_level,
            },
        )
        return goal


def implementation_ready(context_variables: dict[str, Any]) -> bool:
    """Return the typed judge decision; prose output is never authoritative."""

    decision = context_variables.get("suggestion_dict")
    return isinstance(decision, dict) and decision.get("fully_correct") is True
