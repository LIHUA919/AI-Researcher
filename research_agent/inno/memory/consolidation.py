"""Memory consolidation: episodes -> durable facts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ConsolidatedFact:
    """A durable fact extracted from conversation episodes."""

    content: str
    source_episodes: List[str] = field(default_factory=list)
    salience: float = 0.5
    recency: float = 0.5
    novelty: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)


class MemoryConsolidator:
    """Consolidates raw episodes into durable semantic facts.

    Uses an LLM (via litellm) for extraction, but the scoring and
    pruning logic is deterministic.
    """

    def __init__(self, model: str = "gpt-4o") -> None:
        self._model = model

    def consolidate(
        self,
        episodes: List[dict],
        extract_fn: Optional[callable] = None,
    ) -> List[ConsolidatedFact]:
        """Extract facts from episodes.

        Args:
            episodes: List of episode dicts (from MemoryStore.add_episode).
            extract_fn: Optional custom extraction function. If None, uses
                        a simple heuristic (summary-based).
        """
        if extract_fn is not None:
            return extract_fn(episodes)

        # Simple heuristic: each episode with a summary becomes a fact.
        facts: List[ConsolidatedFact] = []
        for ep in episodes:
            summary = ep.get("summary", "")
            if not summary:
                continue
            facts.append(
                ConsolidatedFact(
                    content=summary,
                    source_episodes=[ep.get("episode_id", "")],
                )
            )
        return facts

    @staticmethod
    def score_importance(fact: ConsolidatedFact) -> float:
        """Compute importance score.

        Higher is more important.
        Forget probability = (1 - salience) * (1 - recency) * (1 - novelty)
        Importance = 1 - forget_probability
        """
        forget = (1 - fact.salience) * (1 - fact.recency) * (1 - fact.novelty)
        return 1.0 - forget

    @staticmethod
    def prune(
        facts: List[ConsolidatedFact],
        max_count: int = 100,
    ) -> List[ConsolidatedFact]:
        """Remove lowest-importance facts to stay within max_count."""
        if len(facts) <= max_count:
            return list(facts)
        scored = sorted(
            facts,
            key=lambda f: MemoryConsolidator.score_importance(f),
            reverse=True,
        )
        return scored[:max_count]
