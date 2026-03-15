"""Integration tests for the full tool discovery lifecycle."""

import textwrap
from pathlib import Path

import pytest

from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.events import SkillEvent, SkillEventBus
from research_agent.inno.skills.registry import SkillRegistry


@pytest.fixture
def fresh_registry():
    SkillRegistry._instance = None
    reg = SkillRegistry()
    yield reg
    SkillRegistry._instance = None


@pytest.fixture
def skill_dir(tmp_path):
    """Create two skills for lifecycle testing."""
    for name, desc, tools in [
        ("alpha", "Alpha skill for searching", ["alpha_search"]),
        ("beta", "Beta skill for processing data", ["beta_process", "beta_clean"]),
    ]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            textwrap.dedent(f"""\
            # {name}

            ## Name
            {name}

            ## Description
            {desc}

            ## Tools
            """
            )
            + "\n".join(f"- {t}" for t in tools)
            + "\n\n## Tags\n- test\n\n## Instructions\nUse the tools.\n"
        )
        tool_fns = "\n".join(
            f'    def {t}() -> str:\n        """{t} tool."""\n        return "{t}"'
            for t in tools
        )
        (d / "__init__.py").write_text(
            f"def get_tools(**kwargs):\n{tool_fns}\n    return [{', '.join(tools)}]\n"
        )
    return tmp_path


class TestFullLifecycle:
    def test_scan_search_load_event_card(self, fresh_registry, skill_dir):
        # Wire up the loader to our test skill dir
        fresh_registry._loader.skill_dirs = [Path(skill_dir)]

        # 1. Scan
        manifests = fresh_registry.loader.scan()
        assert "alpha" in manifests
        assert "beta" in manifests

        # 2. Track events
        events = []
        bus = SkillEventBus()
        import research_agent.inno.skills.registry as reg_mod

        original_bus = reg_mod.skill_event_bus
        reg_mod.skill_event_bus = bus
        bus.subscribe(lambda e: events.append(e))

        try:
            # 3. Register a skill directly (skip Python import since tmp_path
            #    is outside the research_agent package)
            manifest = manifests["alpha"]

            def alpha_search() -> str:
                return "alpha"

            skill = Skill(manifest=manifest, functions=[alpha_search])
            fresh_registry.register_skill(skill)

            assert len(events) == 1
            assert events[0].event_type == "loaded"
            assert events[0].skill_name == "alpha"

            # 4. Export card
            card = fresh_registry.to_agent_card(name="TestAgent")
            assert card.name == "TestAgent"
            assert len(card.capabilities) == 1
            assert card.capabilities[0].name == "alpha"

            # 5. Unload
            fresh_registry.unload_skill("alpha")
            assert len(events) == 2
            assert events[1].event_type == "unloaded"
        finally:
            reg_mod.skill_event_bus = original_bus

    def test_schema_available_before_load(self, skill_dir):
        """Verify tool schemas are readable from manifest without loading Python."""
        from research_agent.inno.skills.loader import SkillLoader

        # Create a skill with parameters
        s = skill_dir / "gamma"
        s.mkdir()
        (s / "SKILL.md").write_text(
            textwrap.dedent("""\
            # gamma

            ## Name
            gamma

            ## Description
            Gamma skill

            ## Tools
            - gamma_run

            ## Parameters
            ```json
            {
              "gamma_run": {
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"]
              }
            }
            ```
            """)
        )
        (s / "__init__.py").write_text(
            "def get_tools(**kwargs):\n"
            '    def gamma_run(x: int) -> str:\n        return str(x)\n'
            "    return [gamma_run]\n"
        )

        loader = SkillLoader(skill_dirs=[str(skill_dir)])
        manifests = loader.scan()
        # Schema is available without loading Python
        assert "gamma_run" in manifests["gamma"].tool_schemas
        assert manifests["gamma"].tool_schemas["gamma_run"]["properties"]["x"]["type"] == "integer"
