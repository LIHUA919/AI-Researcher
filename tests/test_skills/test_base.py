"""Tests for Skill and SkillManifest data models."""

import pytest

from research_agent.inno.skills.base import Skill, SkillDependency, SkillManifest


class TestSkillDependency:
    def test_defaults(self):
        dep = SkillDependency(skill_name="foo")
        assert dep.skill_name == "foo"
        assert dep.optional is False

    def test_optional(self):
        dep = SkillDependency(skill_name="bar", optional=True)
        assert dep.optional is True


class TestSkillManifest:
    def test_defaults(self):
        m = SkillManifest(name="test")
        assert m.name == "test"
        assert m.version == "0.1.0"
        assert m.tools == []
        assert m.dependencies == []
        assert m.required_config == []
        assert m.tags == []
        assert m.instructions == ""
        assert m.source_path is None

    def test_full_construction(self):
        m = SkillManifest(
            name="arxiv_search",
            version="1.0.0",
            description="Search arXiv papers",
            author="HKUDS",
            tools=["search_arxiv", "download_arxiv_source"],
            dependencies=[
                SkillDependency(skill_name="paper_search", optional=True)
            ],
            required_config=["OPENAI_API_KEY"],
            instructions="Use search_arxiv to find papers.",
            tags=["research", "arxiv"],
        )
        assert len(m.tools) == 2
        assert m.dependencies[0].optional is True
        assert m.author == "HKUDS"


class TestSkill:
    def test_name_from_manifest(self):
        m = SkillManifest(name="test_skill")
        s = Skill(manifest=m, functions=[])
        assert s.name == "test_skill"

    def test_tool_names(self):
        def fake_tool():
            pass

        m = SkillManifest(name="t")
        s = Skill(manifest=m, functions=[fake_tool])
        assert s.tool_names == ["fake_tool"]

    def test_get_tool_found(self):
        def tool_a():
            pass

        def tool_b():
            pass

        s = Skill(manifest=SkillManifest(name="t"), functions=[tool_a, tool_b])
        assert s.get_tool("tool_a") is tool_a
        assert s.get_tool("tool_b") is tool_b

    def test_get_tool_not_found(self):
        s = Skill(manifest=SkillManifest(name="t"), functions=[])
        assert s.get_tool("nonexistent") is None

    def test_instructions_property(self):
        m = SkillManifest(name="t", instructions="Do X then Y.")
        s = Skill(manifest=m)
        assert s.instructions == "Do X then Y."

    def test_empty_functions_default(self):
        s = Skill(manifest=SkillManifest(name="t"))
        assert s.functions == []
        assert s.tool_names == []
