"""Namespaced state access for individual agents."""

from __future__ import annotations

from typing import Any, List, Optional

from research_agent.inno.memory.session_state import SessionState


class AgentNamespace:
    """Provides a namespaced view of SessionState for a single agent.

    Keys are stored as ``{agent_name}/{key}`` to prevent collisions.
    Shared keys use no prefix.
    """

    def __init__(self, agent_name: str, session_state: SessionState) -> None:
        self._agent_name = agent_name
        self._state = session_state

    @property
    def agent_name(self) -> str:
        return self._agent_name

    # --- Namespaced access ---

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(f"{self._agent_name}/{key}", default)

    def set(self, key: str, value: Any) -> None:
        self._state.set(f"{self._agent_name}/{key}", value, agent_name=self._agent_name)

    # --- Shared access ---

    def get_shared(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_shared(self, key: str, value: Any) -> None:
        self._state.set(key, value, agent_name=self._agent_name)

    # --- Cross-agent read ---

    def read_from(self, other_agent: str, key: str, default: Any = None) -> Any:
        """Read a key from another agent's namespace (read-only)."""
        return self._state.get(f"{other_agent}/{key}", default)

    # --- Backward compat ---

    def to_context_variables(self) -> dict:
        """Flatten namespaced keys into a plain dict.

        Returns all keys belonging to this agent (without prefix) plus
        all shared keys (those without a '/' separator).
        """
        prefix = f"{self._agent_name}/"
        result = {}
        for key in self._state.keys():
            if key.startswith(prefix):
                result[key[len(prefix):]] = self._state.get(key)
            elif "/" not in key:
                result[key] = self._state.get(key)
        return result
