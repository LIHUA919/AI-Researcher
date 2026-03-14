"""Tests for SkillLoader."""

import os
import tempfile
from pathlib import Path

import pytest

from research_agent.inno.skills.errors import SkillLoadError, SkillNotFoundError
from research_agent.inno.skills.loader import SkillLoader


@pytest.fixture
def skill_tmpdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _make_skill(base: Path, name: str, skill_md: str, init_py: str = None):
    """Helper: create a minimal skill directory."""
    d = base / name
    d.mkdir()
    (d / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if init_py is not None:
        (d / "__init__.py").write_text(init_py, encoding="utf-8")


class TestScan:
    def test_scan_finds_skills(self, skill_tmpdir):
        _make_skill(
            skill_tmpdir,
            "my_skill",
            "# my_skill\n\n## Name\nmy_skill\n\n## Description\nA test.\n",
        )
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        manifests = loader.scan()
        assert "my_skill" in manifests
        assert manifests["my_skill"].description == "A test."

    def test_scan_ignores_dirs_without_skill_md(self, skill_tmpdir):
        (skill_tmpdir / "not_a_skill").mkdir()
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        assert loader.scan() == {}

    def test_scan_ignores_files(self, skill_tmpdir):
        (skill_tmpdir / "readme.txt").write_text("hello")
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        assert loader.scan() == {}

    def test_scan_parses_all_sections(self, skill_tmpdir):
        md = """# full

## Name
full_skill

## Version
2.0.0

## Description
A complete test skill.

## Author
TestAuthor

## Tools
- tool_one
- tool_two

## Dependencies
- other_skill
- optional_dep (optional)

## Required Config
- API_KEY

## Tags
- test
- demo

## Instructions
Use tool_one for X and tool_two for Y.
"""
        _make_skill(skill_tmpdir, "full_skill", md)
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        manifests = loader.scan()
        m = manifests["full_skill"]
        assert m.version == "2.0.0"
        assert m.author == "TestAuthor"
        assert m.tools == ["tool_one", "tool_two"]
        assert len(m.dependencies) == 2
        assert m.dependencies[0].skill_name == "other_skill"
        assert m.dependencies[0].optional is False
        assert m.dependencies[1].skill_name == "optional_dep"
        assert m.dependencies[1].optional is True
        assert m.required_config == ["API_KEY"]
        assert "test" in m.tags
        assert "demo" in m.tags
        assert "tool_one" in m.instructions

    def test_list_available(self, skill_tmpdir):
        _make_skill(skill_tmpdir, "a", "# a\n\n## Name\na\n")
        _make_skill(skill_tmpdir, "b", "# b\n\n## Name\nb\n")
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        available = loader.list_available()
        assert sorted(available) == ["a", "b"]

    def test_scan_nonexistent_dir(self):
        loader = SkillLoader(skill_dirs=["/nonexistent/path"])
        assert loader.scan() == {}


class TestLoad:
    def test_load_raises_on_missing_skill(self, skill_tmpdir):
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        with pytest.raises(SkillNotFoundError):
            loader.load("no_such_skill")

    def test_load_raises_on_missing_get_tools(self, skill_tmpdir):
        _make_skill(
            skill_tmpdir,
            "bad_skill",
            "# bad\n\n## Name\nbad_skill\n",
            init_py="x = 1\n",
        )
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        loader.scan()
        # Can't actually import from tmpdir without sys.path manipulation,
        # so this tests the path resolution error case
        with pytest.raises(SkillLoadError):
            loader.load("bad_skill")


class TestParsing:
    def test_parse_list_helper(self):
        text = "- alpha\n- beta\n  \nnot a list\n- gamma"
        result = SkillLoader._parse_list(text)
        assert result == ["alpha", "beta", "gamma"]

    def test_parse_empty_list(self):
        assert SkillLoader._parse_list("") == []
        assert SkillLoader._parse_list("no list items here") == []

    def test_name_fallback_to_directory(self, skill_tmpdir):
        """If ## Name section is missing, use directory name."""
        _make_skill(
            skill_tmpdir,
            "dirname_skill",
            "# Something\n\n## Description\nHello\n",
        )
        loader = SkillLoader(skill_dirs=[str(skill_tmpdir)])
        manifests = loader.scan()
        assert "dirname_skill" in manifests
