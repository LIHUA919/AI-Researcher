import pytest

from research_agent.inno.experience import (
    BestFirstSearchPolicy,
    CandidateEvaluation,
    CandidateSearchRequest,
    HypothesisCandidate,
    RecallContext,
    RecallRequest,
    ResourceUsage,
    RoundRobinSearchPolicy,
    SearchBudget,
    SearchBudgetExceeded,
    StaticCandidateGenerator,
)
from tests.test_experience.test_ledger import build_records


def recall():
    return RecallContext(
        snapshot_id="recall-snapshot",
        memory_snapshot_id="memory-snapshot",
        request=RecallRequest(
            query="q",
            task_id="task-vq",
            domain="vision",
            dataset_id="cifar10",
            model_family="vq",
        ),
        items=[],
        token_count=0,
    )


def candidates():
    hypotheses = [build_records(suffix=str(index))[0] for index in range(1, 4)]
    return [
        HypothesisCandidate(
            candidate_id="candidate-1",
            hypothesis=hypotheses[0],
            prior_score=0.9,
        ),
        HypothesisCandidate(
            candidate_id="candidate-2",
            hypothesis=hypotheses[1],
            parent_candidate_id="candidate-1",
            prior_score=0.8,
        ),
        HypothesisCandidate(
            candidate_id="candidate-3",
            hypothesis=hypotheses[2],
            parent_candidate_id="candidate-1",
            prior_score=0.1,
        ),
    ]


def request(*, direction="maximize", max_candidates=3):
    return CandidateSearchRequest(
        task_id="task-vq",
        query="find the best hypothesis",
        direction=direction,
        recall=recall(),
        budget=SearchBudget(
            max_candidates=max_candidates,
            max_tokens=300,
            max_wall_seconds=30,
            max_gpu_hours=0,
        ),
    )


class FakeEvaluator:
    def __init__(self, scores, usage=None):
        self.scores = scores
        self.usage = usage or ResourceUsage(tokens=50, wall_seconds=1)

    def evaluate(self, candidate, allocation):
        return CandidateEvaluation(
            candidate_id=candidate.candidate_id,
            score=self.scores[candidate.candidate_id],
            valid=True,
            usage=self.usage,
            verification_id=f"verification:{candidate.candidate_id}",
        )


def test_best_first_search_respects_shared_budget_and_lineage():
    result = BestFirstSearchPolicy().search(
        request(max_candidates=2),
        StaticCandidateGenerator(candidates()),
        FakeEvaluator(
            {
                "candidate-1": 0.5,
                "candidate-2": 0.8,
                "candidate-3": 0.9,
            }
        ),
    )

    assert [item.candidate_id for item in result.evaluations] == [
        "candidate-1",
        "candidate-2",
    ]
    assert result.selected is not None
    assert result.selected.candidate_id == "candidate-2"
    assert result.usage.tokens == 100
    assert result.exhausted is True
    assert result.lineage["candidate-2"] == "candidate-1"
    assert result.memory_snapshot_id == "recall-snapshot"
    assert result.search_gain == pytest.approx(0.3)


def test_round_robin_is_a_second_policy_adapter_and_supports_minimize():
    result = RoundRobinSearchPolicy().search(
        request(direction="minimize"),
        StaticCandidateGenerator(candidates()),
        FakeEvaluator(
            {
                "candidate-1": 0.7,
                "candidate-2": 0.4,
                "candidate-3": 0.6,
            }
        ),
    )

    assert result.policy == "round-robin"
    assert result.selected is not None
    assert result.selected.candidate_id == "candidate-2"
    assert result.search_gain == pytest.approx(0.3)


def test_invalid_candidates_are_not_selected():
    class InvalidEvaluator:
        def evaluate(self, candidate, allocation):
            return CandidateEvaluation(
                candidate_id=candidate.candidate_id,
                score=999,
                valid=False,
                usage=ResourceUsage(),
                failure_reason="invalid verification",
            )

    result = BestFirstSearchPolicy().search(
        request(),
        StaticCandidateGenerator(candidates()),
        InvalidEvaluator(),
    )

    assert result.selected is None
    assert result.search_gain == 0


def test_evaluator_cannot_exceed_shared_allocation():
    with pytest.raises(SearchBudgetExceeded):
        BestFirstSearchPolicy().search(
            request(),
            StaticCandidateGenerator(candidates()),
            FakeEvaluator(
                {
                    "candidate-1": 1,
                    "candidate-2": 1,
                    "candidate-3": 1,
                },
                usage=ResourceUsage(tokens=301),
            ),
        )


def test_unknown_parent_lineage_is_rejected():
    bad = candidates()[0].model_copy(update={"parent_candidate_id": "missing"})

    with pytest.raises(ValueError, match="unknown parent"):
        BestFirstSearchPolicy().search(
            request(),
            StaticCandidateGenerator([bad]),
            FakeEvaluator({"candidate-1": 1}),
        )


def test_cyclic_lineage_is_rejected():
    first, second, _ = candidates()
    cycle = [
        first.model_copy(update={"parent_candidate_id": second.candidate_id}),
        second.model_copy(update={"parent_candidate_id": first.candidate_id}),
    ]

    with pytest.raises(ValueError, match="acyclic"):
        BestFirstSearchPolicy().search(
            request(),
            StaticCandidateGenerator(cycle),
            FakeEvaluator({"candidate-1": 1, "candidate-2": 2}),
        )
