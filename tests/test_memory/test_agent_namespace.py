"""Tests for AgentNamespace."""

import pytest

from research_agent.inno.memory.agent_namespace import AgentNamespace
from research_agent.inno.memory.session_state import SessionState


@pytest.fixture
def state():
    return SessionState()


class TestNamespacedIsolation:
    def test_two_agents_same_key(self, state):
        ns_a = AgentNamespace("A", state)
        ns_b = AgentNamespace("B", state)
        ns_a.set("result", "from A")
        ns_b.set("result", "from B")
        assert ns_a.get("result") == "from A"
        assert ns_b.get("result") == "from B"

    def test_get_default(self, state):
        ns = AgentNamespace("A", state)
        assert ns.get("missing", "default") == "default"


class TestSharedNamespace:
    def test_shared_write_and_read(self, state):
        ns_a = AgentNamespace("A", state)
        ns_b = AgentNamespace("B", state)
        ns_a.set_shared("global_key", "shared_value")
        assert ns_b.get_shared("global_key") == "shared_value"


class TestCrossAgentRead:
    def test_read_from_other_agent(self, state):
        ns_a = AgentNamespace("A", state)
        ns_b = AgentNamespace("B", state)
        ns_a.set("plan", "my plan")
        assert ns_b.read_from("A", "plan") == "my plan"

    def test_read_from_nonexistent(self, state):
        ns = AgentNamespace("A", state)
        assert ns.read_from("nobody", "x", "fallback") == "fallback"


class TestContextVariables:
    def test_to_context_variables(self, state):
        ns_a = AgentNamespace("A", state)
        ns_a.set("x", 1)
        ns_a.set("y", 2)
        ns_a.set_shared("global", 3)
        cv = ns_a.to_context_variables()
        assert cv["x"] == 1
        assert cv["y"] == 2
        assert cv["global"] == 3

    def test_excludes_other_agents(self, state):
        ns_a = AgentNamespace("A", state)
        ns_b = AgentNamespace("B", state)
        ns_a.set("a_key", 1)
        ns_b.set("b_key", 2)
        cv = ns_a.to_context_variables()
        assert "a_key" in cv
        assert "b_key" not in cv
