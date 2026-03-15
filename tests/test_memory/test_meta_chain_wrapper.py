"""Tests for MemoryAwareMetaChain wrapper."""

from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

import pytest

from research_agent.inno.memory.meta_chain_wrapper import MemoryAwareMetaChain
from research_agent.inno.memory.store import MemoryStore


@dataclass
class FakeAgent:
    name: str = "TestAgent"


@dataclass
class FakeResponse:
    messages: list
    agent: object = None
    context_variables: dict = None

    def __post_init__(self):
        if self.context_variables is None:
            self.context_variables = {}


@pytest.fixture
def store():
    return MemoryStore(project_path="", platform="local")


@pytest.fixture
def mock_chain():
    chain = MagicMock()
    chain.run.return_value = FakeResponse(
        messages=[{"role": "assistant", "content": "done"}],
        context_variables={"result": "ok"},
    )
    return chain


@pytest.fixture
def wrapper(mock_chain, store):
    return MemoryAwareMetaChain(mock_chain, store)


class TestDelegation:
    def test_delegates_to_meta_chain(self, wrapper, mock_chain):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "hello"}])
        assert mock_chain.run.called

    def test_passes_context_variables(self, wrapper, mock_chain):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "hi"}], context_variables={"a": 1})
        call_kwargs = mock_chain.run.call_args
        cv = call_kwargs.kwargs.get("context_variables") or call_kwargs[1].get("context_variables", {})
        assert "a" in cv


class TestMemoryRecording:
    def test_records_episode(self, wrapper, store):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "test"}])
        episodes = store.query_episodes("completed")
        assert len(episodes) == 1

    def test_merges_response_context(self, wrapper, store):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "test"}])
        assert store.session.get("result") == "ok"


class TestEventLog:
    def test_logs_start_and_end(self, wrapper):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "test"}])
        events = wrapper.event_log.query(agent_name="TestAgent")
        assert len(events) == 2
        assert events[0].data["action"] == "start"
        assert events[1].data["action"] == "end"


class TestBackwardCompat:
    def test_plain_dict_context(self, wrapper, mock_chain):
        agent = FakeAgent()
        wrapper.run(agent, [{"role": "user", "content": "hi"}], context_variables={"x": 1})
        cv = mock_chain.run.call_args.kwargs.get("context_variables", {})
        assert isinstance(cv, dict)
