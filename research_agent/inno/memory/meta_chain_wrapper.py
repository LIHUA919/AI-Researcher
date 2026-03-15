"""MemoryAwareMetaChain: opt-in wrapper for MetaChain with memory."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from research_agent.inno.memory.agent_namespace import AgentNamespace
from research_agent.inno.memory.event_log import EventLog, make_event
from research_agent.inno.memory.store import MemoryStore

if TYPE_CHECKING:
    from research_agent.inno.core import MetaChain
    from research_agent.inno.types import Agent, Response


class MemoryAwareMetaChain:
    """Wraps MetaChain to add memory features without modifying core.py.

    Usage::

        meta_chain = MetaChain()
        memory_store = MemoryStore(project_path="/workspace")
        mem_chain = MemoryAwareMetaChain(meta_chain, memory_store)
        response = mem_chain.run(agent, messages)
    """

    def __init__(
        self,
        meta_chain: "MetaChain",
        memory_store: MemoryStore,
        event_log: Optional[EventLog] = None,
    ) -> None:
        self._chain = meta_chain
        self._store = memory_store
        self._event_log = event_log or EventLog()

    @property
    def memory_store(self) -> MemoryStore:
        return self._store

    @property
    def event_log(self) -> EventLog:
        return self._event_log

    def run(
        self,
        agent: "Agent",
        messages: List,
        context_variables: Optional[dict] = None,
        **kwargs,
    ) -> "Response":
        """Run with memory: inject context, delegate, record episode."""
        # Before: merge incoming context into session state
        if context_variables:
            self._store.session.merge(context_variables, agent_name=agent.name)

        # Create namespace for this agent
        ns = AgentNamespace(agent.name, self._store.session)

        # Log agent start event
        self._event_log.append(
            make_event("agent_transfer", agent.name, {"action": "start"})
        )

        # Delegate to real MetaChain
        cv = self._store.session.to_context_variables()
        response = self._chain.run(
            agent=agent,
            messages=messages,
            context_variables=cv,
            **kwargs,
        )

        # After: record episode
        self._store.add_episode(
            agent_name=agent.name,
            messages=response.messages,
            summary=f"Agent {agent.name} completed a turn.",
        )

        # Merge returned context back into session state
        if response.context_variables:
            self._store.session.merge(
                response.context_variables, agent_name=agent.name
            )

        # Log completion event
        self._event_log.append(
            make_event("agent_transfer", agent.name, {"action": "end"})
        )

        return response

    async def run_async(
        self,
        agent: "Agent",
        messages: List,
        context_variables: Optional[dict] = None,
        **kwargs,
    ) -> "Response":
        """Async run with memory."""
        if context_variables:
            self._store.session.merge(context_variables, agent_name=agent.name)

        self._event_log.append(
            make_event("agent_transfer", agent.name, {"action": "start"})
        )

        cv = self._store.session.to_context_variables()
        response = await self._chain.run_async(
            agent=agent,
            messages=messages,
            context_variables=cv,
            **kwargs,
        )

        self._store.add_episode(
            agent_name=agent.name,
            messages=response.messages,
            summary=f"Agent {agent.name} completed an async turn.",
        )

        if response.context_variables:
            self._store.session.merge(
                response.context_variables, agent_name=agent.name
            )

        self._event_log.append(
            make_event("agent_transfer", agent.name, {"action": "end"})
        )

        return response
