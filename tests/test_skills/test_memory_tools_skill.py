"""Tests for the memory_tools skill."""

import pytest

from research_agent.inno.memory.store import MemoryStore
from research_agent.inno.skills.loader import SkillLoader


@pytest.fixture
def store():
    s = MemoryStore(project_path="", platform="local")
    s.add_episode("A", [{"role": "user", "content": "research GNN"}], "Researched GNNs")
    return s


class TestSkillMdParses:
    def test_manifest_loads(self):
        loader = SkillLoader()
        manifests = loader.scan()
        assert "memory_tools" in manifests
        m = manifests["memory_tools"]
        assert "recall_memory" in m.tools
        assert "store_memory" in m.tools
        assert len(m.tool_schemas) == 4


class TestGetToolsReturns:
    def test_returns_four_callables(self, store):
        from research_agent.inno.skills.memory_tools import get_tools

        tools = get_tools(memory_store=store)
        assert len(tools) == 4
        for t in tools:
            assert callable(t)


class TestRecallMemory:
    def test_recall_finds_episode(self, store):
        from research_agent.inno.skills.memory_tools import get_tools

        tools = get_tools(memory_store=store)
        recall = tools[0]
        result = recall("GNN")
        assert "GNN" in result

    def test_recall_no_match(self, store):
        from research_agent.inno.skills.memory_tools import get_tools

        tools = get_tools(memory_store=store)
        recall = tools[0]
        result = recall("zzz_nonexistent")
        assert "No memories found" in result


class TestStoreMemory:
    def test_store_and_retrieve(self, store):
        from research_agent.inno.skills.memory_tools import get_tools

        tools = get_tools(memory_store=store)
        store_fn = tools[1]
        result = store_fn("my_key", "my_value")
        assert "Stored" in result
        assert store.session.get("my_key") == "my_value"
