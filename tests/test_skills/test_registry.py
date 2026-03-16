"""Tests for SkillRegistry."""

import pytest

from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.loader import SkillLoader
from research_agent.inno.skills.registry import SkillRegistry


def _make_registry():
    """Create a fresh SkillRegistry instance (bypass singleton for testing)."""
    from research_agent.inno.registry import Registry

    reg = object.__new__(SkillRegistry)
    reg._skills = {}
    reg._loader = SkillLoader()
    reg._base_registry = Registry()
    reg._tool_stacks = {}
    return reg


class TestRegisterAndRetrieve:
    def test_register_skill(self):
        reg = _make_registry()

        def my_tool():
            return "hello"

        skill = Skill(
            manifest=SkillManifest(name="test_skill"),
            functions=[my_tool],
        )
        reg.register_skill(skill)

        assert reg.get_skill("test_skill") is skill
        assert reg.get_skill_tools("test_skill") == [my_tool]
        assert "test_skill" in reg.list_skills()

    def test_get_skill_not_found(self):
        reg = _make_registry()
        assert reg.get_skill("nonexistent") is None
        assert reg.get_skill_tools("nonexistent") == []

    def test_register_injects_into_base_registry(self):
        reg = _make_registry()

        def my_func():
            pass

        skill = Skill(
            manifest=SkillManifest(name="s"),
            functions=[my_func],
        )
        reg.register_skill(skill)
        assert "my_func" in reg._base_registry._registry["tools"]


class TestUnload:
    def test_unload_removes_skill(self):
        reg = _make_registry()

        def tool_x():
            pass

        skill = Skill(
            manifest=SkillManifest(name="removable"),
            functions=[tool_x],
        )
        reg.register_skill(skill)
        assert reg.get_skill("removable") is not None

        reg.unload_skill("removable")
        assert reg.get_skill("removable") is None
        assert "tool_x" not in reg._base_registry._registry["tools"]

    def test_unload_nonexistent_is_noop(self):
        reg = _make_registry()
        reg.unload_skill("does_not_exist")  # Should not raise

    def test_unload_restores_previous_tool_binding(self):
        reg = _make_registry()

        def original():
            return "original"

        def tool_a():
            return "a"

        def tool_b():
            return "b"

        tool_a.__name__ = "shared_tool"
        tool_b.__name__ = "shared_tool"
        reg._base_registry._registry["tools"]["shared_tool"] = original

        reg.register_skill(
            Skill(manifest=SkillManifest(name="a"), functions=[tool_a])
        )
        reg.register_skill(
            Skill(manifest=SkillManifest(name="b"), functions=[tool_b])
        )

        reg.unload_skill("a")
        assert reg._base_registry._registry["tools"]["shared_tool"] is tool_b

        reg.unload_skill("b")
        assert reg._base_registry._registry["tools"]["shared_tool"] is original


class TestInstructions:
    def test_compose_instructions(self):
        reg = _make_registry()
        s1 = Skill(
            manifest=SkillManifest(name="a", instructions="Use tool A."),
            functions=[],
        )
        s2 = Skill(
            manifest=SkillManifest(name="b", instructions="Use tool B."),
            functions=[],
        )
        reg.register_skill(s1)
        reg.register_skill(s2)

        combined = reg.get_instructions_for_skills(["a", "b"])
        assert "Use tool A." in combined
        assert "Use tool B." in combined
        assert "## Skill: a" in combined
        assert "## Skill: b" in combined

    def test_compose_skips_missing_skills(self):
        reg = _make_registry()
        s1 = Skill(
            manifest=SkillManifest(name="a", instructions="Hello."),
            functions=[],
        )
        reg.register_skill(s1)

        combined = reg.get_instructions_for_skills(["a", "nonexistent"])
        assert "Hello." in combined

    def test_compose_skips_empty_instructions(self):
        reg = _make_registry()
        s1 = Skill(
            manifest=SkillManifest(name="empty", instructions=""),
            functions=[],
        )
        reg.register_skill(s1)

        combined = reg.get_instructions_for_skills(["empty"])
        assert combined == ""
