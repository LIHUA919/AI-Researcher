"""Session state with change tracking for backward-compatible context_variables."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class StateChange:
    """A single recorded mutation to session state."""

    key: str
    value: Any
    agent_name: str
    timestamp: datetime
    previous_value: Any


class SessionState:
    """Drop-in replacement for the flat context_variables dict.

    Adds typed access, change tracking, and history while remaining
    backward-compatible via ``to_context_variables()``.
    """

    def __init__(self, initial_vars: Optional[dict] = None) -> None:
        self._data: Dict[str, Any] = dict(initial_vars or {})
        self._history: Dict[str, List[StateChange]] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, agent_name: str = "") -> None:
        prev = self._data.get(key)
        self._data[key] = value
        change = StateChange(
            key=key,
            value=value,
            agent_name=agent_name,
            timestamp=datetime.now(),
            previous_value=prev,
        )
        self._history.setdefault(key, []).append(change)

    def history(self, key: str) -> List[StateChange]:
        return list(self._history.get(key, []))

    def snapshot(self) -> dict:
        """Return an independent deep copy of all current key-value pairs."""
        return copy.deepcopy(self._data)

    def to_context_variables(self) -> dict:
        """Return the raw dict for backward compatibility with MetaChain.run()."""
        return self._data

    def merge(self, other_vars: dict, agent_name: str = "") -> None:
        """Bulk-merge a dict into state, recording each key change."""
        for key, value in other_vars.items():
            self.set(key, value, agent_name=agent_name)

    def keys_changed_since(self, timestamp: datetime) -> List[str]:
        """Return keys that have been modified since *timestamp*."""
        changed = set()
        for key, changes in self._history.items():
            for c in changes:
                if c.timestamp > timestamp:
                    changed.add(key)
                    break
        return sorted(changed)

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)
