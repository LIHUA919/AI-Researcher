"""Structured traces for goal-driven research evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional


SourceType = Literal["paper", "repo", "web", "code", "tool_output", "other"]


@dataclass(slots=True)
class RetrievalItem:
    """A retrieved evidence candidate produced during a run."""

    source_type: SourceType
    identifier: str
    title: str
    content: str = ""
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolCallTrace:
    """Trace for a single tool invocation."""

    agent_name: str
    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    latency_ms: Optional[int] = None
    output_summary: str = ""
    error_message: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class AgentStepTrace:
    """High-level trace for one agent turn or handoff."""

    agent_name: str
    input_summary: str = ""
    output_summary: str = ""
    transferred_to: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class ResearchRunTrace:
    """End-to-end trace for a research run under evaluation."""

    run_id: str
    task_id: str
    query: str
    goal: str = ""
    final_output: Dict[str, Any] = field(default_factory=dict)
    plan: Dict[str, Any] = field(default_factory=dict)
    claims: List[str] = field(default_factory=list)
    retrieved_items: List[RetrievalItem] = field(default_factory=list)
    tool_calls: List[ToolCallTrace] = field(default_factory=list)
    agent_steps: List[AgentStepTrace] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def add_retrieval(self, item: RetrievalItem) -> None:
        self.retrieved_items.append(item)

    def add_tool_call(self, tool_call: ToolCallTrace) -> None:
        self.tool_calls.append(tool_call)

    def add_agent_step(self, step: AgentStepTrace) -> None:
        self.agent_steps.append(step)

    def mark_completed(self) -> None:
        self.completed_at = datetime.utcnow()
