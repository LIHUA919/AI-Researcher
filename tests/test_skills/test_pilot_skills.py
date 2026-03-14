"""Tests for the 5 pilot skills."""

import pytest

from research_agent.inno.skills.loader import SkillLoader


PILOT_SKILLS = [
    "arxiv_search",
    "paper_search",
    "planning",
    "code_search",
    "file_operations",
]


class TestPilotSkillDiscovery:
    def test_all_pilot_skills_discoverable(self):
        loader = SkillLoader()
        manifests = loader.scan()
        for name in PILOT_SKILLS:
            assert name in manifests, f"Skill '{name}' not found"

    def test_all_manifests_have_required_fields(self):
        loader = SkillLoader()
        manifests = loader.scan()
        for name in PILOT_SKILLS:
            m = manifests[name]
            assert m.name == name
            assert len(m.description) > 0, f"{name} missing description"
            assert len(m.tools) > 0, f"{name} missing tools"
            assert len(m.instructions) > 0, f"{name} missing instructions"

    def test_manifest_versions(self):
        loader = SkillLoader()
        manifests = loader.scan()
        for name in PILOT_SKILLS:
            assert manifests[name].version == "0.1.0"


class TestPilotSkillLoading:
    def test_arxiv_search_loads(self):
        loader = SkillLoader()
        loader.scan()
        skill = loader.load("arxiv_search")
        assert len(skill.functions) >= 3
        names = skill.tool_names
        assert "search_arxiv" in names

    def test_paper_search_loads(self):
        loader = SkillLoader()
        loader.scan()
        skill = loader.load("paper_search")
        assert len(skill.functions) >= 1
        assert "get_arxiv_paper_meta" in skill.tool_names

    def test_planning_loads(self):
        loader = SkillLoader()
        loader.scan()
        skill = loader.load("planning")
        names = skill.tool_names
        assert "plan_dataset" in names
        assert "plan_model" in names
        assert "plan_training" in names
        assert "plan_testing" in names

    def test_code_search_loads(self):
        loader = SkillLoader()
        loader.scan()
        skill = loader.load("code_search")
        names = skill.tool_names
        assert "search_github_repos" in names

    def test_file_operations_loads_without_env(self):
        loader = SkillLoader()
        loader.scan()
        skill = loader.load("file_operations")
        assert len(skill.functions) >= 5
        names = skill.tool_names
        assert "read_file" in names
        assert "write_file" in names

    def test_all_loaded_functions_are_callable(self):
        loader = SkillLoader()
        loader.scan()
        for name in PILOT_SKILLS:
            skill = loader.load(name)
            for f in skill.functions:
                assert callable(f), f"{name}/{f.__name__} is not callable"
