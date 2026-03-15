"""Tests for JSON Schema support in SKILL.md and SkillManifest."""

import textwrap
from pathlib import Path

import pytest

from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.loader import SkillLoader


@pytest.fixture
def skill_dir(tmp_path):
    """Create a temporary skill directory with a Parameters section."""
    skill = tmp_path / "test_skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        textwrap.dedent("""\
        # test_skill

        ## Name
        test_skill

        ## Version
        0.2.0

        ## Description
        A test skill with parameters.

        ## Tools
        - do_stuff
        - do_more

        ## Parameters
        ```json
        {
          "do_stuff": {
            "type": "object",
            "properties": {
              "query": {"type": "string"},
              "count": {"type": "integer"}
            },
            "required": ["query"]
          },
          "do_more": {
            "type": "object",
            "properties": {
              "path": {"type": "string"}
            },
            "required": ["path"]
          }
        }
        ```

        ## Tags
        - test

        ## Instructions
        Use do_stuff to test.
        """)
    )
    (skill / "__init__.py").write_text(
        textwrap.dedent("""\
        def get_tools(**kwargs):
            def do_stuff(query: str, count: int = 5) -> str:
                \"\"\"Do stuff.\"\"\"
                return f"{query} {count}"
            def do_more(path: str) -> str:
                \"\"\"Do more.\"\"\"
                return path
            return [do_stuff, do_more]
        """)
    )
    return tmp_path


@pytest.fixture
def skill_dir_no_params(tmp_path):
    """Create a skill directory without a Parameters section."""
    skill = tmp_path / "simple_skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        textwrap.dedent("""\
        # simple_skill

        ## Name
        simple_skill

        ## Version
        0.1.0

        ## Description
        A skill without parameters.

        ## Tools
        - hello

        ## Instructions
        Just say hello.
        """)
    )
    (skill / "__init__.py").write_text(
        textwrap.dedent("""\
        def get_tools(**kwargs):
            def hello(name: str) -> str:
                \"\"\"Say hello.\"\"\"
                return f"Hello {name}"
            return [hello]
        """)
    )
    return tmp_path


class TestManifestParsesToolSchemas:
    def test_manifest_has_tool_schemas(self, skill_dir):
        loader = SkillLoader(skill_dirs=[str(skill_dir)])
        manifests = loader.scan()
        m = manifests["test_skill"]
        assert "do_stuff" in m.tool_schemas
        assert "do_more" in m.tool_schemas
        assert m.tool_schemas["do_stuff"]["properties"]["query"]["type"] == "string"
        assert m.tool_schemas["do_stuff"]["required"] == ["query"]

    def test_manifest_without_parameters_has_empty_schemas(self, skill_dir_no_params):
        loader = SkillLoader(skill_dirs=[str(skill_dir_no_params)])
        manifests = loader.scan()
        m = manifests["simple_skill"]
        assert m.tool_schemas == {}


class TestSkillGetToolSchema:
    def test_get_schema_from_manifest(self, skill_dir):
        loader = SkillLoader(skill_dirs=[str(skill_dir)])
        loader.scan()
        # We build a Skill manually to test get_tool_schema
        manifest = loader.get_manifest("test_skill")

        def do_stuff(query: str, count: int = 5) -> str:
            """Do stuff."""
            return f"{query} {count}"

        skill = Skill(manifest=manifest, functions=[do_stuff])
        schema = skill.get_tool_schema("do_stuff")
        assert schema is not None
        assert schema["properties"]["query"]["type"] == "string"

    def test_get_schema_fallback_to_function(self, skill_dir_no_params):
        loader = SkillLoader(skill_dirs=[str(skill_dir_no_params)])
        loader.scan()
        manifest = loader.get_manifest("simple_skill")

        def hello(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"

        skill = Skill(manifest=manifest, functions=[hello])
        schema = skill.get_tool_schema("hello")
        assert schema is not None
        assert "name" in schema["properties"]

    def test_get_schema_unknown_tool_returns_none(self, skill_dir):
        loader = SkillLoader(skill_dirs=[str(skill_dir)])
        loader.scan()
        manifest = loader.get_manifest("test_skill")
        skill = Skill(manifest=manifest, functions=[])
        assert skill.get_tool_schema("nonexistent") is None


class TestParseParameters:
    def test_parse_empty(self):
        assert SkillLoader._parse_parameters("") == {}

    def test_parse_json_block(self):
        text = '''
```json
{
  "tool_a": {"type": "object", "properties": {"x": {"type": "string"}}}
}
```
'''
        result = SkillLoader._parse_parameters(text)
        assert "tool_a" in result
        assert result["tool_a"]["properties"]["x"]["type"] == "string"

    def test_parse_invalid_json_skipped(self):
        text = '''
```json
not valid json
```
'''
        assert SkillLoader._parse_parameters(text) == {}
