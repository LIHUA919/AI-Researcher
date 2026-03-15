"""In-process event bus for skill lifecycle events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Literal, Optional

from research_agent.inno.skills.base import SkillManifest


@dataclass
class SkillEvent:
    """An event emitted when a skill is loaded, unloaded, or changed."""

    event_type: Literal["loaded", "unloaded", "changed"]
    skill_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    manifest: Optional[SkillManifest] = None


class SkillEventBus:
    """Simple synchronous pub/sub for skill lifecycle events."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, Callable[[SkillEvent], None]] = {}

    def subscribe(self, callback: Callable[[SkillEvent], None]) -> str:
        """Register a callback; returns a subscription ID."""
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscription by ID."""
        self._subscribers.pop(sub_id, None)

    def publish(self, event: SkillEvent) -> None:
        """Notify all subscribers synchronously."""
        for callback in list(self._subscribers.values()):
            callback(event)

    def clear(self) -> None:
        """Remove all subscribers."""
        self._subscribers.clear()


# Module-level singleton
skill_event_bus = SkillEventBus()
