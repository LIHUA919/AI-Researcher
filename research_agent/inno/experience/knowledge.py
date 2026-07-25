from __future__ import annotations

import hashlib
import json
import string

from research_agent.inno.experience.models import (
    ExperienceRecord,
    KnowledgeRecord,
    PromotionDecision,
)


class KnowledgeGate:
    def __init__(
        self,
        *,
        domain: str,
        model_family: str,
        policy_version: str = "1",
    ) -> None:
        self.domain = domain
        self.model_family = model_family
        self.policy_version = policy_version

    def decide(
        self,
        experience: ExperienceRecord,
        related: list[ExperienceRecord],
    ) -> tuple[PromotionDecision, KnowledgeRecord | None]:
        reasons = self._rejection_reasons(experience, related)
        if reasons:
            return self._decision(experience, reasons=reasons), None

        verification = experience.verification
        assert verification is not None
        consistent = [
            item
            for item in related
            if item.verification is not None
            and item.verification.valid
            and item.verification.outcome == verification.outcome
            and item.task_id == experience.task_id
        ]
        sources = sorted(
            {experience.experience_id, *(item.experience_id for item in consistent)}
        )
        confidence = round(min(0.99, 0.7 + 0.1 * len(consistent)), 2)
        knowledge_payload = {
            "task_id": experience.task_id,
            "domain": self.domain,
            "dataset_id": experience.attempt.dataset_id,
            "model_family": self.model_family,
            "lesson": experience.analysis.strip(),
            "conditions": experience.hypothesis.conditions,
            "outcome": verification.outcome,
            "confidence": confidence,
            "source_experience_ids": sources,
            "promotion_policy_version": self.policy_version,
        }
        knowledge_id = hashlib.sha256(
            json.dumps(
                knowledge_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        knowledge = KnowledgeRecord(
            knowledge_id=knowledge_id,
            created_at=experience.created_at,
            **knowledge_payload,
        )
        return (
            self._decision(
                experience,
                reasons=["eligible_verified_experience"],
                knowledge_id=knowledge_id,
            ),
            knowledge,
        )

    def _rejection_reasons(
        self,
        experience: ExperienceRecord,
        related: list[ExperienceRecord],
    ) -> list[str]:
        verification = experience.verification
        reasons: list[str] = []
        if verification is None:
            return ["missing_verification"]
        if experience.attempt.status != "completed":
            reasons.append(f"attempt_not_completed:{experience.attempt.status}")
        if experience.observation.exit_code != 0:
            reasons.append(
                f"observation_exit_code:{experience.observation.exit_code}"
            )
        if not verification.valid:
            reasons.append("invalid_verification")
        if verification.outcome not in {"positive", "negative"}:
            reasons.append("non_reusable_outcome")
        if verification.outcome == "positive" and not verification.passed:
            reasons.append("inconsistent_positive_outcome")
        if verification.outcome == "negative" and verification.passed:
            reasons.append("inconsistent_negative_outcome")
        required_comparison = {"metric", "baseline", "value", "delta", "direction"}
        if not required_comparison.issubset(verification.baseline_comparison):
            reasons.append("incomplete_baseline_comparison")
        if not experience.observation.artifact_refs:
            reasons.append("missing_evidence_artifacts")
        elif any(not self._valid_digest(ref.sha256) for ref in experience.observation.artifact_refs):
            reasons.append("invalid_artifact_digest")
        if not experience.analysis.strip():
            reasons.append("missing_lesson")
        if not experience.hypothesis.conditions:
            reasons.append("missing_conditions")

        opposite = {
            "positive": "negative",
            "negative": "positive",
        }.get(verification.outcome)
        if opposite and any(
            item.task_id == experience.task_id
            and item.verification is not None
            and item.verification.valid
            and item.verification.outcome == opposite
            for item in related
        ):
            reasons.append("contradictory_verified_experience")
        return reasons

    @staticmethod
    def _valid_digest(digest: str) -> bool:
        return len(digest) == 64 and all(character in string.hexdigits for character in digest)

    def _decision(
        self,
        experience: ExperienceRecord,
        *,
        reasons: list[str],
        knowledge_id: str | None = None,
    ) -> PromotionDecision:
        payload = {
            "experience_id": experience.experience_id,
            "accepted": knowledge_id is not None,
            "reasons": reasons,
            "policy_version": self.policy_version,
            "knowledge_id": knowledge_id,
        }
        decision_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return PromotionDecision(
            decision_id=decision_id,
            created_at=experience.created_at,
            **payload,
        )
