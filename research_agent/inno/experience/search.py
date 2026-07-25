from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from research_agent.inno.experience.models import Hypothesis, RecallContext


class SearchBudgetExceeded(RuntimeError):
    """Raised when a candidate evaluator exceeds its allocated shared budget."""


class ResourceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tokens: int = Field(default=0, ge=0)
    wall_seconds: float = Field(default=0.0, ge=0)
    gpu_hours: float = Field(default=0.0, ge=0)

    def add(self, other: "ResourceUsage") -> "ResourceUsage":
        return ResourceUsage(
            tokens=self.tokens + other.tokens,
            wall_seconds=self.wall_seconds + other.wall_seconds,
            gpu_hours=self.gpu_hours + other.gpu_hours,
        )


class SearchBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_candidates: int = Field(ge=1)
    max_tokens: int = Field(ge=0)
    max_wall_seconds: float = Field(ge=0)
    max_gpu_hours: float = Field(ge=0)

    def remaining(self, used: ResourceUsage) -> ResourceUsage:
        return ResourceUsage(
            tokens=max(0, self.max_tokens - used.tokens),
            wall_seconds=max(0.0, self.max_wall_seconds - used.wall_seconds),
            gpu_hours=max(0.0, self.max_gpu_hours - used.gpu_hours),
        )


class HypothesisCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    hypothesis: Hypothesis
    parent_candidate_id: str | None = None
    prior_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    score: float
    valid: bool
    usage: ResourceUsage
    verification_id: str | None = None
    failure_reason: str | None = None


class CandidateSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    query: str
    direction: Literal["maximize", "minimize"]
    recall: RecallContext
    budget: SearchBudget


class CandidateSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy: str
    memory_snapshot_id: str
    selected: HypothesisCandidate | None
    evaluations: list[CandidateEvaluation]
    lineage: dict[str, str | None]
    usage: ResourceUsage
    exhausted: bool
    search_gain: float


class CandidateGenerator(Protocol):
    def generate(self, request: CandidateSearchRequest) -> list[HypothesisCandidate]: ...


class CandidateEvaluator(Protocol):
    def evaluate(
        self,
        candidate: HypothesisCandidate,
        allocation: ResourceUsage,
    ) -> CandidateEvaluation: ...


class SearchPolicy(Protocol):
    def search(
        self,
        request: CandidateSearchRequest,
        generator: CandidateGenerator,
        evaluator: CandidateEvaluator,
    ) -> CandidateSearchResult: ...


class StaticCandidateGenerator:
    def __init__(self, candidates: list[HypothesisCandidate]) -> None:
        self.candidates = list(candidates)

    def generate(self, request: CandidateSearchRequest) -> list[HypothesisCandidate]:
        return list(self.candidates)


class _OrderedSearchPolicy:
    name = "ordered"

    def order(
        self,
        candidates: list[HypothesisCandidate],
    ) -> list[HypothesisCandidate]:
        return candidates

    def search(
        self,
        request: CandidateSearchRequest,
        generator: CandidateGenerator,
        evaluator: CandidateEvaluator,
    ) -> CandidateSearchResult:
        generated = generator.generate(request)
        self._validate_lineage(generated)
        ordered = self.order(generated)
        evaluations: list[CandidateEvaluation] = []
        candidates_by_id = {item.candidate_id: item for item in generated}
        usage = ResourceUsage()

        for candidate in ordered:
            if len(evaluations) >= request.budget.max_candidates:
                break
            allocation = request.budget.remaining(usage)
            evaluation = evaluator.evaluate(candidate, allocation)
            if evaluation.candidate_id != candidate.candidate_id:
                raise ValueError("candidate evaluator returned a mismatched candidate_id")
            self._validate_usage(evaluation.usage, allocation)
            evaluations.append(evaluation)
            usage = usage.add(evaluation.usage)

        valid = [item for item in evaluations if item.valid]
        selected_evaluation = self._select(valid, request.direction)
        selected = (
            candidates_by_id[selected_evaluation.candidate_id]
            if selected_evaluation is not None
            else None
        )
        return CandidateSearchResult(
            policy=self.name,
            memory_snapshot_id=request.recall.snapshot_id,
            selected=selected,
            evaluations=evaluations,
            lineage={
                candidate.candidate_id: candidate.parent_candidate_id
                for candidate in generated
            },
            usage=usage,
            exhausted=len(evaluations) < len(generated),
            search_gain=self._search_gain(valid, request.direction),
        )

    @staticmethod
    def _validate_lineage(candidates: list[HypothesisCandidate]) -> None:
        ids = {item.candidate_id for item in candidates}
        if len(ids) != len(candidates):
            raise ValueError("candidate IDs must be unique")
        for item in candidates:
            if item.parent_candidate_id is not None and item.parent_candidate_id not in ids:
                raise ValueError(
                    f"unknown parent candidate: {item.parent_candidate_id}"
                )
            if item.parent_candidate_id == item.candidate_id:
                raise ValueError("candidate cannot be its own parent")
        parents = {
            item.candidate_id: item.parent_candidate_id for item in candidates
        }
        for candidate_id in parents:
            seen: set[str] = set()
            current: str | None = candidate_id
            while current is not None:
                if current in seen:
                    raise ValueError("candidate lineage must be acyclic")
                seen.add(current)
                current = parents[current]

    @staticmethod
    def _validate_usage(used: ResourceUsage, allocation: ResourceUsage) -> None:
        if (
            used.tokens > allocation.tokens
            or used.wall_seconds > allocation.wall_seconds
            or used.gpu_hours > allocation.gpu_hours
        ):
            raise SearchBudgetExceeded("candidate evaluator exceeded shared budget")

    @staticmethod
    def _select(
        evaluations: list[CandidateEvaluation],
        direction: Literal["maximize", "minimize"],
    ) -> CandidateEvaluation | None:
        if not evaluations:
            return None
        return sorted(
            evaluations,
            key=lambda item: (
                -item.score if direction == "maximize" else item.score,
                item.candidate_id,
            ),
        )[0]

    @staticmethod
    def _search_gain(
        evaluations: list[CandidateEvaluation],
        direction: Literal["maximize", "minimize"],
    ) -> float:
        if len(evaluations) < 2:
            return 0.0
        first = evaluations[0].score
        best = (
            max(item.score for item in evaluations)
            if direction == "maximize"
            else min(item.score for item in evaluations)
        )
        gain = best - first if direction == "maximize" else first - best
        return round(gain, 12)


class BestFirstSearchPolicy(_OrderedSearchPolicy):
    name = "best-first"

    def order(
        self,
        candidates: list[HypothesisCandidate],
    ) -> list[HypothesisCandidate]:
        return sorted(candidates, key=lambda item: (-item.prior_score, item.candidate_id))


class RoundRobinSearchPolicy(_OrderedSearchPolicy):
    name = "round-robin"
