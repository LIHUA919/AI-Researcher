"""Tests for MemoryStore."""

import pytest

from research_agent.inno.memory.store import MemoryStore


@pytest.fixture
def store():
    return MemoryStore(project_path="", platform="local")


class TestSessionProperty:
    def test_session_state_accessible(self, store):
        store.session.set("x", 1)
        assert store.session.get("x") == 1


class TestEpisodes:
    def test_add_and_query(self, store):
        eid = store.add_episode(
            agent_name="A",
            messages=[{"role": "user", "content": "find papers on transformers"}],
            summary="Searched for transformer papers",
        )
        assert isinstance(eid, str)
        results = store.query_episodes("transformer")
        assert len(results) == 1
        assert results[0]["agent_name"] == "A"

    def test_query_by_agent(self, store):
        store.add_episode("A", [{"role": "user", "content": "hello"}], "hello from A")
        store.add_episode("B", [{"role": "user", "content": "hello"}], "hello from B")
        results = store.query_episodes("hello", agent_name="A")
        assert len(results) == 1
        assert results[0]["agent_name"] == "A"

    def test_query_no_match(self, store):
        store.add_episode("A", [{"role": "user", "content": "foo"}], "foo")
        results = store.query_episodes("zzz_no_match")
        assert results == []


class TestAgentContext:
    def test_includes_session(self, store):
        store.session.set("key", "val")
        ctx = store.get_agent_context("A")
        assert ctx["key"] == "val"

    def test_includes_recent_episodes(self, store):
        store.add_episode("A", [{"role": "user", "content": "test"}], "ep1")
        ctx = store.get_agent_context("A")
        assert "_recent_episodes" in ctx
        assert len(ctx["_recent_episodes"]) == 1
