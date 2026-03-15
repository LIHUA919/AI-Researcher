"""Tests for A2A Agent Card export."""

import json
import textwrap
from pathlib import Path

import pytest

from research_agent.inno.skills.agent_card import AgentCard, AgentCapability, build_agent_card
from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.registry import SkillRegistry


def _make_skill(name, tools, description="", tags=None):
    manifest = SkillManifest(
        name=name,
        description=description,
        tools=tools,
        tags=tags or [],
    )

    def dummy():
        pass

    fns = []
    for t in tools:
        fn = lambda: None
        fn.__name__ = t
        fns.append(fn)
    return Skill(manifest=manifest, functions=fns)


@pytest.fixture
def fresh_registry():
    """Create a fresh registry (not the singleton) for isolated tests."""
    SkillRegistry._instance = None
    reg = SkillRegistry()
    yield reg
    SkillRegistry._instance = None


class TestAgentCard:
    def test_empty_registry_produces_empty_card(self, fresh_registry):
        card = build_agent_card(fresh_registry)
        assert card.name == "AI-Researcher"
        assert card.capabilities == []

    def test_card_with_skills(self, fresh_registry):
        s1 = _make_skill("arxiv", ["search_arxiv"], "Search arXiv", ["research"])
        s2 = _make_skill("code", ["search_code"], "Search code", ["code"])
        fresh_registry.register_skill(s1)
        fresh_registry.register_skill(s2)
        card = build_agent_card(fresh_registry)
        assert len(card.capabilities) == 2
        names = [c.name for c in card.capabilities]
        assert "arxiv" in names
        assert "code" in names

    def test_card_includes_tool_names(self, fresh_registry):
        s = _make_skill("test", ["tool_a", "tool_b"], "Test skill")
        fresh_registry.register_skill(s)
        card = build_agent_card(fresh_registry)
        assert card.capabilities[0].tools == ["tool_a", "tool_b"]

    def test_card_includes_tags(self, fresh_registry):
        s = _make_skill("test", ["t"], tags=["research", "ml"])
        fresh_registry.register_skill(s)
        card = build_agent_card(fresh_registry)
        assert "research" in card.capabilities[0].tags

    def test_card_json_serialization(self, fresh_registry):
        s = _make_skill("test", ["tool_a"], "Test")
        fresh_registry.register_skill(s)
        card = build_agent_card(fresh_registry)
        j = card.to_json()
        parsed = json.loads(j)
        assert parsed["name"] == "AI-Researcher"
        assert len(parsed["capabilities"]) == 1

    def test_to_agent_card_on_registry(self, fresh_registry):
        s = _make_skill("test", ["tool_a"], "Test")
        fresh_registry.register_skill(s)
        card = fresh_registry.to_agent_card(name="MyAgent", url="http://localhost")
        assert card.name == "MyAgent"
        assert card.url == "http://localhost"
