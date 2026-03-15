"""memory_tools skill: Agent-callable memory operations."""

from __future__ import annotations

import json
from typing import Callable, List


def get_tools(**kwargs) -> List[Callable]:
    """Return memory tool functions.

    Expects ``memory_store`` in kwargs (a MemoryStore instance).
    If not provided, tools return informative error messages.
    """
    memory_store = kwargs.get("memory_store", None)

    def recall_memory(query: str, top_k: int = 5) -> str:
        """Search past episodes and facts for information matching the query."""
        if memory_store is None:
            return "Memory store not available."
        episodes = memory_store.query_episodes(query, top_k=top_k)
        if not episodes:
            return f"No memories found for: {query}"
        results = []
        for ep in episodes:
            results.append(
                f"[{ep.get('agent_name', '?')}] {ep.get('summary', 'No summary')}"
            )
        return "\n".join(results)

    def store_memory(key: str, value: str, shared: bool = False) -> str:
        """Store a key-value pair in session state."""
        if memory_store is None:
            return "Memory store not available."
        if shared:
            memory_store.session.set(key, value)
        else:
            memory_store.session.set(key, value)
        return f"Stored '{key}' = '{value}'"

    def search_episodes(query: str, agent_name: str = "") -> str:
        """Search past conversation episodes."""
        if memory_store is None:
            return "Memory store not available."
        episodes = memory_store.query_episodes(
            query, agent_name=agent_name or None
        )
        if not episodes:
            return f"No episodes found for: {query}"
        results = []
        for ep in episodes:
            results.append(
                f"[{ep['agent_name']}] {ep.get('summary', '')} "
                f"({len(ep.get('messages', []))} messages)"
            )
        return "\n".join(results)

    def get_agent_state(agent_name: str = "") -> str:
        """Get the current state snapshot for an agent (or full state)."""
        if memory_store is None:
            return "Memory store not available."
        if agent_name:
            ctx = memory_store.get_agent_context(agent_name)
        else:
            ctx = memory_store.session.snapshot()
        return json.dumps(ctx, default=str, indent=2)

    return [recall_memory, store_memory, search_episodes, get_agent_state]
