"""Tests for the event log."""

from datetime import datetime, timedelta

import pytest

from research_agent.inno.memory.event_log import AgentEvent, EventLog, make_event


@pytest.fixture
def log():
    return EventLog(backend="memory")


def _event(etype="tool_call", agent="A", data=None):
    return make_event(etype, agent, data)


class TestAppendCount:
    def test_append_and_count(self, log):
        for _ in range(5):
            log.append(_event())
        assert log.count() == 5

    def test_append_returns_id(self, log):
        eid = log.append(_event())
        assert isinstance(eid, str) and len(eid) > 0


class TestQuery:
    def test_query_by_agent(self, log):
        log.append(_event(agent="A"))
        log.append(_event(agent="B"))
        log.append(_event(agent="A"))
        results = log.query(agent_name="A")
        assert len(results) == 2

    def test_query_by_event_type(self, log):
        log.append(_event(etype="tool_call"))
        log.append(_event(etype="state_change"))
        log.append(_event(etype="tool_call"))
        results = log.query(event_type="tool_call")
        assert len(results) == 2

    def test_query_since(self, log):
        log.append(_event())
        before = datetime.now()
        log.append(_event())
        results = log.query(since=before)
        assert len(results) >= 1

    def test_query_limit(self, log):
        for _ in range(10):
            log.append(_event())
        results = log.query(limit=3)
        assert len(results) == 3


class TestReplay:
    def test_replay_all(self, log):
        ids = [log.append(_event()) for _ in range(5)]
        replayed = log.replay()
        assert len(replayed) == 5

    def test_replay_from_event_id(self, log):
        e1 = _event()
        e2 = _event()
        e3 = _event()
        log.append(e1)
        log.append(e2)
        log.append(e3)
        replayed = log.replay(from_event_id=e1.event_id)
        assert len(replayed) == 2  # e2 and e3 (after e1)


class TestMakeEvent:
    def test_make_event_fields(self):
        e = make_event("tool_call", "AgentX", {"tool": "search"})
        assert e.event_type == "tool_call"
        assert e.agent_name == "AgentX"
        assert e.data["tool"] == "search"
        assert isinstance(e.timestamp, datetime)
        assert len(e.event_id) > 0
