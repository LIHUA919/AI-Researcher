"""Tests for the skill event bus."""

from datetime import datetime

import pytest

from research_agent.inno.skills.base import SkillManifest
from research_agent.inno.skills.events import SkillEvent, SkillEventBus


@pytest.fixture
def bus():
    return SkillEventBus()


def _make_event(event_type="loaded", name="test_skill"):
    return SkillEvent(
        event_type=event_type,
        skill_name=name,
        manifest=SkillManifest(name=name),
    )


class TestSubscribePublish:
    def test_callback_invoked(self, bus):
        received = []
        bus.subscribe(lambda e: received.append(e))
        event = _make_event()
        bus.publish(event)
        assert len(received) == 1
        assert received[0].skill_name == "test_skill"

    def test_multiple_subscribers(self, bus):
        a, b = [], []
        bus.subscribe(lambda e: a.append(e))
        bus.subscribe(lambda e: b.append(e))
        bus.publish(_make_event())
        assert len(a) == 1
        assert len(b) == 1


class TestUnsubscribe:
    def test_unsubscribed_not_invoked(self, bus):
        received = []
        sub_id = bus.subscribe(lambda e: received.append(e))
        bus.unsubscribe(sub_id)
        bus.publish(_make_event())
        assert received == []

    def test_unsubscribe_unknown_is_noop(self, bus):
        bus.unsubscribe("nonexistent")  # should not raise


class TestEventData:
    def test_event_fields(self):
        event = _make_event("unloaded", "my_skill")
        assert event.event_type == "unloaded"
        assert event.skill_name == "my_skill"
        assert isinstance(event.timestamp, datetime)

    def test_event_without_manifest(self):
        event = SkillEvent(event_type="loaded", skill_name="x")
        assert event.manifest is None


class TestClear:
    def test_clear_removes_all(self, bus):
        received = []
        bus.subscribe(lambda e: received.append(e))
        bus.clear()
        bus.publish(_make_event())
        assert received == []
