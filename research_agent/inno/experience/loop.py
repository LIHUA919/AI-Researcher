from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict

from research_agent.inno.experience.evaluation import EvaluationContract, Verifier
from research_agent.inno.experience.knowledge import KnowledgeGate
from research_agent.inno.experience.ledger import ExperimentLedger
from research_agent.inno.experience.models import (
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    Observation,
    RecallContext,
    RecallRequest,
    VerificationRecord,
)
from research_agent.inno.experience.retrieval import ExperienceRetriever
from research_agent.inno.experience.transaction import ExperimentTransaction


ExperienceMode = Literal["off", "record", "recall", "closed-loop"]
LoopAction = Literal["continue", "completed", "failed_budget", "invalid", "unverified"]
EventSink = Callable[[str, dict[str, Any]], None]


class RunCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    hypothesis: Hypothesis
    attempt: ExperimentAttempt
    observation: Observation
    analysis: str
    iteration_number: int
    max_iterations: int


class LoopOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: LoopAction
    experience: ExperienceRecord | None = None
    verification: VerificationRecord | None = None
    knowledge_id: str | None = None
    reason: str = ""


class ExperienceLoop:
    def __init__(
        self,
        *,
        ledger: ExperimentLedger,
        retriever: ExperienceRetriever,
        verifier: Verifier,
        knowledge_gate: KnowledgeGate,
        evaluation_contract: EvaluationContract,
        mode: ExperienceMode = "closed-loop",
        event_sink: EventSink | None = None,
    ) -> None:
        self.ledger = ledger
        self.retriever = retriever
        self.verifier = verifier
        self.knowledge_gate = knowledge_gate
        self.evaluation_contract = evaluation_contract
        self.mode = mode
        self.event_sink = event_sink

    def before_run(self, request: RecallRequest) -> RecallContext:
        self._emit("recall_started", {"task_id": request.task_id, "mode": self.mode})
        if self.mode not in {"recall", "closed-loop"}:
            context = self._empty_context(request)
            self._emit(
                "recall_completed",
                {"snapshot_id": context.snapshot_id, "item_count": 0, "skipped": True},
            )
            return context
        try:
            context = self.retriever.recall(request)
        except Exception as exc:
            context = self._empty_context(request)
            self._emit(
                "recall_failed",
                {"error": type(exc).__name__, "snapshot_id": context.snapshot_id},
            )
            return context
        self._emit(
            "recall_completed",
            {
                "snapshot_id": context.snapshot_id,
                "item_count": len(context.items),
                "token_count": context.token_count,
            },
        )
        return context

    def after_run(self, completion: RunCompletion) -> LoopOutcome:
        if self.mode not in {"record", "closed-loop"}:
            return LoopOutcome(action="unverified", reason="experience_recording_disabled")
        transaction = ExperimentTransaction(
            ledger=self.ledger,
            verifier=self.verifier,
            knowledge_gate=self.knowledge_gate,
            evaluation_contract=self.evaluation_contract,
            event_sink=self.event_sink,
        )
        transaction_result = transaction.commit(completion)
        experience = transaction_result.experience
        verification = transaction_result.verification
        knowledge = transaction_result.knowledge

        if (
            completion.attempt.status != "completed"
            or completion.observation.exit_code != 0
        ):
            action = "invalid"
            reason = "attempt_failed"
        elif not verification.valid:
            action: LoopAction = (
                "continue"
                if completion.iteration_number < completion.max_iterations
                else "invalid"
            )
            reason = "verification_invalid"
        elif verification.passed:
            action = "completed"
            reason = "primary_metric_improved"
        elif completion.iteration_number < completion.max_iterations:
            action = "continue"
            reason = "verified_non_positive_result"
            self._emit(
                "iteration_scheduled",
                {"next_iteration": completion.iteration_number + 1},
            )
        else:
            action = "failed_budget"
            reason = "iteration_budget_exhausted"

        self._emit(
            "loop_completed",
            {"action": action, "experience_id": experience.experience_id},
        )
        return LoopOutcome(
            action=action,
            experience=experience,
            verification=verification,
            knowledge_id=knowledge.knowledge_id if knowledge is not None else None,
            reason=reason,
        )

    def _empty_context(self, request: RecallRequest) -> RecallContext:
        memory_snapshot_id = self.ledger.snapshot_id()
        payload = json.dumps(
            {
                "memory_snapshot_id": memory_snapshot_id,
                "request": request.model_dump(mode="json"),
                "items": [],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return RecallContext(
            snapshot_id=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            memory_snapshot_id=memory_snapshot_id,
            request=request,
            items=[],
            token_count=0,
        )

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(event_type, payload)
