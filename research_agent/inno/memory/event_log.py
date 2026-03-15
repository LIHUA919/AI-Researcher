"""Append-only event log for agent lifecycle and state changes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional


@dataclass
class AgentEvent:
    """A single recorded event in the agent lifecycle."""

    event_id: str
    event_type: Literal["state_change", "tool_call", "agent_transfer", "message", "error"]
    agent_name: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)


class InMemoryBackend:
    """List-backed storage for event logs."""

    def __init__(self) -> None:
        self._events: List[AgentEvent] = []

    def append(self, event: AgentEvent) -> None:
        self._events.append(event)

    def query(
        self,
        agent_name: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AgentEvent]:
        results = self._events
        if agent_name is not None:
            results = [e for e in results if e.agent_name == agent_name]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if since is not None:
            results = [e for e in results if e.timestamp > since]
        return results[-limit:]

    def replay(self, from_event_id: Optional[str] = None) -> List[AgentEvent]:
        if from_event_id is None:
            return list(self._events)
        found = False
        out: List[AgentEvent] = []
        for e in self._events:
            if found:
                out.append(e)
            if e.event_id == from_event_id:
                found = True
        return out

    def count(self) -> int:
        return len(self._events)


class EventLog:
    """Append-only event log with pluggable backends.

    Default backend is in-memory. Redis backend is a stub for future use.
    """

    def __init__(self, backend: str = "memory") -> None:
        if backend == "memory":
            self._backend = InMemoryBackend()
        else:
            raise ValueError(f"Unknown backend: {backend}. Use 'memory'.")

    def append(self, event: AgentEvent) -> str:
        self._backend.append(event)
        return event.event_id

    def query(
        self,
        agent_name: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AgentEvent]:
        return self._backend.query(
            agent_name=agent_name,
            event_type=event_type,
            since=since,
            limit=limit,
        )

    def replay(self, from_event_id: Optional[str] = None) -> List[AgentEvent]:
        return self._backend.replay(from_event_id=from_event_id)

    def count(self) -> int:
        return self._backend.count()


def make_event(
    event_type: str,
    agent_name: str,
    data: Optional[dict] = None,
) -> AgentEvent:
    """Convenience factory for creating events."""
    return AgentEvent(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        agent_name=agent_name,
        timestamp=datetime.now(),
        data=data or {},
    )
