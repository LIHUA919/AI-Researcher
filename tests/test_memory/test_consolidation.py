"""Tests for memory consolidation."""

import pytest

from research_agent.inno.memory.consolidation import ConsolidatedFact, MemoryConsolidator


@pytest.fixture
def consolidator():
    return MemoryConsolidator()


class TestScoreImportance:
    def test_high_scores(self):
        f = ConsolidatedFact(content="x", salience=0.9, recency=0.9, novelty=0.9)
        score = MemoryConsolidator.score_importance(f)
        assert score > 0.99  # 1 - 0.1*0.1*0.1 = 0.999

    def test_low_scores(self):
        f = ConsolidatedFact(content="x", salience=0.1, recency=0.1, novelty=0.1)
        score = MemoryConsolidator.score_importance(f)
        assert score < 0.5  # 1 - 0.9*0.9*0.9 = 0.271


class TestPrune:
    def test_prune_keeps_top(self):
        facts = [
            ConsolidatedFact(content=f"f{i}", salience=i * 0.1, recency=0.5, novelty=0.5)
            for i in range(10)
        ]
        pruned = MemoryConsolidator.prune(facts, max_count=3)
        assert len(pruned) == 3
        # Highest salience should survive
        assert pruned[0].content == "f9"

    def test_prune_under_limit(self):
        facts = [ConsolidatedFact(content="a"), ConsolidatedFact(content="b")]
        pruned = MemoryConsolidator.prune(facts, max_count=10)
        assert len(pruned) == 2


class TestConsolidate:
    def test_heuristic_from_summaries(self, consolidator):
        episodes = [
            {"episode_id": "e1", "summary": "Found paper on GNNs"},
            {"episode_id": "e2", "summary": "Ran experiment"},
            {"episode_id": "e3", "summary": ""},  # no summary -> skipped
        ]
        facts = consolidator.consolidate(episodes)
        assert len(facts) == 2
        assert facts[0].content == "Found paper on GNNs"

    def test_custom_extract_fn(self, consolidator):
        def custom(eps):
            return [ConsolidatedFact(content="custom")]

        facts = consolidator.consolidate([], extract_fn=custom)
        assert len(facts) == 1
        assert facts[0].content == "custom"
