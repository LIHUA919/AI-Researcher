"""Unified memory store wrapping existing memory classes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from research_agent.inno.memory.session_state import SessionState


class MemoryStore:
    """Single entry-point for all memory tiers.

    Wraps existing Memory classes (lazy init) and adds episode storage.
    Does NOT modify existing classes.
    """

    def __init__(
        self,
        project_path: str = "",
        platform: str = "local",
    ) -> None:
        self._project_path = project_path
        self._platform = platform
        self._session = SessionState()
        self._episodes: List[Dict[str, Any]] = []
        self._agent_memory = None
        self._code_memory = None
        self._paper_memory = None

    @property
    def session(self) -> SessionState:
        return self._session

    @property
    def agent_memory(self):
        """Lazily create the base Memory instance."""
        if self._agent_memory is None:
            from research_agent.inno.memory.rag_memory import Memory

            self._agent_memory = Memory(
                project_path=self._project_path,
                platform=self._platform,
            )
        return self._agent_memory

    @property
    def code_memory(self):
        """Lazily create a CodeMemory instance."""
        if self._code_memory is None:
            from research_agent.inno.memory.code_memory import CodeMemory

            self._code_memory = CodeMemory(
                project_path=self._project_path,
                platform=self._platform,
            )
        return self._code_memory

    @property
    def paper_memory(self):
        """Lazily create a PaperMemory instance."""
        if self._paper_memory is None:
            from research_agent.inno.memory.paper_memory import PaperMemory

            self._paper_memory = PaperMemory(
                project_path=self._project_path,
                platform=self._platform,
            )
        return self._paper_memory

    # --- Episode management ---

    def add_episode(
        self,
        agent_name: str,
        messages: List[dict],
        summary: str = "",
    ) -> str:
        """Store a conversation episode and return its ID."""
        episode_id = str(uuid.uuid4())
        self._episodes.append(
            {
                "episode_id": episode_id,
                "agent_name": agent_name,
                "messages": messages,
                "summary": summary,
                "timestamp": datetime.now().isoformat(),
            }
        )
        return episode_id

    def query_episodes(
        self,
        query: str,
        agent_name: Optional[str] = None,
        top_k: int = 5,
    ) -> List[dict]:
        """Retrieve relevant past episodes (simple keyword match).

        A production implementation would use vector search; this
        provides a working baseline.
        """
        candidates = self._episodes
        if agent_name:
            candidates = [e for e in candidates if e["agent_name"] == agent_name]
        # Simple relevance: episodes whose summary contains the query terms
        query_lower = query.lower()
        scored = []
        for ep in candidates:
            text = (ep.get("summary", "") + " ".join(
                m.get("content", "") for m in ep["messages"] if isinstance(m.get("content"), str)
            )).lower()
            if query_lower in text:
                scored.append(ep)
        return scored[-top_k:]

    def get_agent_context(self, agent_name: str) -> dict:
        """Return combined context from session state + relevant episodes."""
        ctx = self._session.snapshot()
        recent_episodes = [
            e for e in self._episodes if e["agent_name"] == agent_name
        ][-3:]
        if recent_episodes:
            ctx["_recent_episodes"] = recent_episodes
        return ctx
