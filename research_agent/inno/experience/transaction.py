from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Callable, Protocol

from research_agent.inno.experience.evaluation import EvaluationContract, Verifier
from research_agent.inno.experience.knowledge import KnowledgeGate
from research_agent.inno.experience.ledger import (
    ExperimentLedger,
    RecordNotFoundError,
)
from research_agent.inno.experience.models import (
    ExperienceQuery,
    ExperienceRecord,
    ExperimentAttempt,
    Hypothesis,
    KnowledgeRecord,
    Observation,
    TransactionStage,
    TransactionTransition,
    VerificationRecord,
)


EventSink = Callable[[str, dict[str, Any]], None]


class CompletionRecord(Protocol):
    hypothesis: Hypothesis
    attempt: ExperimentAttempt
    observation: Observation
    analysis: str


@dataclass(frozen=True)
class TransactionResult:
    experience: ExperienceRecord
    verification: VerificationRecord
    knowledge: KnowledgeRecord | None


class ExperimentTransaction:
    """Commit or resume one Experiment Attempt through Knowledge promotion."""

    def __init__(
        self,
        *,
        ledger: ExperimentLedger,
        verifier: Verifier,
        knowledge_gate: KnowledgeGate,
        evaluation_contract: EvaluationContract,
        event_sink: EventSink | None = None,
    ) -> None:
        self.ledger = ledger
        self.verifier = verifier
        self.knowledge_gate = knowledge_gate
        self.evaluation_contract = evaluation_contract
        self.event_sink = event_sink

    def commit(self, completion: CompletionRecord) -> TransactionResult:
        self.ledger.append_hypothesis(completion.hypothesis)
        self.ledger.append_attempt(completion.attempt)
        self._transition(
            completion,
            stage="attempt_recorded",
            record_id=completion.attempt.attempt_id,
            created_at=completion.attempt.created_at,
        )
        self._emit("attempt_recorded", {"attempt_id": completion.attempt.attempt_id})

        self.ledger.append_observation(completion.observation)
        self._transition(
            completion,
            stage="observation_recorded",
            record_id=completion.observation.observation_id,
            created_at=completion.observation.completed_at,
        )
        self._emit(
            "observation_recorded",
            {"observation_id": completion.observation.observation_id},
        )

        verification = self.ledger.find_verification(
            completion.observation.observation_id,
            self.evaluation_contract.contract_id,
            self.evaluation_contract.version,
        )
        resumed_verification = verification is not None
        if verification is None:
            self._emit(
                "verification_started",
                {"observation_id": completion.observation.observation_id},
            )
            verification = self.verifier.verify(
                self.evaluation_contract,
                completion.observation,
            )
            self.ledger.append_verification(verification)
        self._transition(
            completion,
            stage="verification_recorded",
            record_id=verification.verification_id,
            created_at=verification.created_at,
        )
        self._emit(
            "verification_completed",
            {
                "verification_id": verification.verification_id,
                "valid": verification.valid,
                "outcome": verification.outcome,
                "resumed": resumed_verification,
            },
        )

        experience = self._experience(completion, verification)
        try:
            experience = self.ledger.get_experience(experience.experience_id)
            resumed_experience = True
        except RecordNotFoundError:
            self.ledger.append_experience(experience)
            resumed_experience = False
        self._transition(
            completion,
            stage="experience_recorded",
            record_id=experience.experience_id,
            created_at=experience.created_at,
        )
        self._emit(
            "experience_recorded",
            {
                "experience_id": experience.experience_id,
                "resumed": resumed_experience,
            },
        )

        decision = self.ledger.find_promotion_decision(
            experience.experience_id,
            self.knowledge_gate.policy_version,
        )
        knowledge: KnowledgeRecord | None = None
        resumed_promotion = decision is not None
        if decision is not None:
            if decision.knowledge_id is not None:
                knowledge = self.ledger.get_knowledge(decision.knowledge_id)
        else:
            related = [
                item
                for item in self.ledger.query(
                    ExperienceQuery(task_id=experience.task_id, valid_only=True)
                )
                if item.experience_id != experience.experience_id
            ]
            decision, knowledge = self.knowledge_gate.decide(experience, related)
            if knowledge is not None:
                self.ledger.append_knowledge(knowledge)
            self.ledger.append_promotion_decision(decision)

        self._transition(
            completion,
            stage="promotion_decided",
            record_id=decision.decision_id,
            created_at=decision.created_at,
        )
        if knowledge is not None:
            self._emit(
                "knowledge_promoted",
                {
                    "knowledge_id": knowledge.knowledge_id,
                    "experience_id": experience.experience_id,
                    "resumed": resumed_promotion,
                },
            )
        else:
            self._emit(
                "knowledge_rejected",
                {
                    "experience_id": experience.experience_id,
                    "reasons": decision.reasons,
                    "resumed": resumed_promotion,
                },
            )
        return TransactionResult(
            experience=experience,
            verification=verification,
            knowledge=knowledge,
        )

    @staticmethod
    def _experience(
        completion: CompletionRecord,
        verification: VerificationRecord,
    ) -> ExperienceRecord:
        payload = {
            "hypothesis_id": completion.hypothesis.hypothesis_id,
            "attempt_id": completion.attempt.attempt_id,
            "observation_id": completion.observation.observation_id,
            "verification_id": verification.verification_id,
        }
        experience_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ExperienceRecord(
            experience_id=experience_id,
            task_id=completion.attempt.task_id,
            hypothesis=completion.hypothesis,
            attempt=completion.attempt,
            observation=completion.observation,
            verification=verification,
            analysis=completion.analysis,
            created_at=completion.observation.completed_at,
        )

    def _transition(
        self,
        completion: CompletionRecord,
        *,
        stage: TransactionStage,
        record_id: str,
        created_at,
    ) -> None:
        transition_payload = {
            "attempt_id": completion.attempt.attempt_id,
            "stage": stage,
            "record_id": record_id,
        }
        transition_id = hashlib.sha256(
            json.dumps(
                transition_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.ledger.append_transition(
            TransactionTransition(
                transition_id=transition_id,
                created_at=created_at,
                **transition_payload,
            )
        )

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(event_type, payload)
