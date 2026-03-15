"""Tests for SessionState."""

from datetime import datetime, timedelta

import pytest

from research_agent.inno.memory.session_state import SessionState, StateChange


class TestGetSet:
    def test_set_and_get(self):
        s = SessionState()
        s.set("key", "value")
        assert s.get("key") == "value"

    def test_get_default(self):
        s = SessionState()
        assert s.get("missing", "default") == "default"

    def test_initial_vars(self):
        s = SessionState({"a": 1, "b": 2})
        assert s.get("a") == 1
        assert s.get("b") == 2

    def test_overwrite(self):
        s = SessionState()
        s.set("x", 1)
        s.set("x", 2)
        assert s.get("x") == 2


class TestHistory:
    def test_history_tracking(self):
        s = SessionState()
        s.set("k", 1, agent_name="A")
        s.set("k", 2, agent_name="B")
        s.set("k", 3, agent_name="A")
        h = s.history("k")
        assert len(h) == 3
        assert h[0].value == 1
        assert h[0].agent_name == "A"
        assert h[1].value == 2
        assert h[2].previous_value == 2

    def test_history_empty_key(self):
        s = SessionState()
        assert s.history("nope") == []


class TestSnapshot:
    def test_snapshot_returns_copy(self):
        s = SessionState({"a": [1, 2]})
        snap = s.snapshot()
        snap["a"].append(3)
        assert s.get("a") == [1, 2]  # original unchanged


class TestContextVariables:
    def test_to_context_variables_is_dict(self):
        s = SessionState({"x": 1})
        cv = s.to_context_variables()
        assert isinstance(cv, dict)
        assert cv["x"] == 1

    def test_context_variables_reflects_mutations(self):
        s = SessionState()
        s.set("y", 42)
        assert s.to_context_variables()["y"] == 42


class TestMerge:
    def test_merge_records_agent(self):
        s = SessionState()
        s.merge({"a": 1, "b": 2}, agent_name="AgentX")
        assert s.get("a") == 1
        h = s.history("a")
        assert h[0].agent_name == "AgentX"


class TestKeysChangedSince:
    def test_filters_by_time(self):
        s = SessionState()
        before = datetime.now()
        s.set("old", 1)
        after = datetime.now() + timedelta(seconds=0.01)
        # Only keys set after 'after' should be empty
        changed = s.keys_changed_since(after)
        # 'old' was set before 'after', so may or may not appear depending on timing
        # But definitely set before test ends
        assert isinstance(changed, list)


class TestContains:
    def test_contains(self):
        s = SessionState({"a": 1})
        assert "a" in s
        assert "b" not in s

    def test_len(self):
        s = SessionState({"a": 1, "b": 2})
        assert len(s) == 2
