"""Integration tests: skills with Agent and function_to_json."""

import pytest

from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.types import Agent
from research_agent.inno.util import function_to_json


class TestFunctionToJsonCompat:
    def test_skill_tool_produces_valid_schema(self):
        """A skill-loaded function must produce a valid OpenAI tool schema."""
        from research_agent.inno.tools.arxiv_source import search_arxiv

        schema = function_to_json(search_arxiv)
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search_arxiv"
        assert "parameters" in schema["function"]

    def test_planning_tools_produce_schemas(self):
        from research_agent.inno.tools.inno_tools.planning_tools import (
            plan_dataset,
            plan_model,
        )

        for tool in [plan_dataset, plan_model]:
            schema = function_to_json(tool)
            assert schema["type"] == "function"
            assert len(schema["function"]["name"]) > 0


class TestAgentCompat:
    def test_skill_functions_assignable_to_agent(self):
        from research_agent.inno.tools.arxiv_source import search_arxiv

        agent = Agent(
            name="Test",
            functions=[search_arxiv],
        )
        assert len(agent.functions) == 1
        assert agent.functions[0].__name__ == "search_arxiv"

    def test_multiple_skill_tools_in_agent(self):
        from research_agent.inno.tools.arxiv_source import search_arxiv
        from research_agent.inno.tools.inno_tools.paper_search import (
            get_arxiv_paper_meta,
        )
        from research_agent.inno.tools.inno_tools.planning_tools import (
            plan_dataset,
        )

        agent = Agent(
            name="Multi-skill Agent",
            functions=[search_arxiv, get_arxiv_paper_meta, plan_dataset],
        )
        assert len(agent.functions) == 3
        names = [f.__name__ for f in agent.functions]
        assert "search_arxiv" in names
        assert "get_arxiv_paper_meta" in names
        assert "plan_dataset" in names


class TestSkillInstructionsInAgent:
    def test_instructions_composable(self):
        from research_agent.inno.skills.registry import SkillRegistry
        from research_agent.inno.skills.loader import SkillLoader

        reg = object.__new__(SkillRegistry)
        reg._skills = {}
        reg._loader = SkillLoader()

        s = Skill(
            manifest=SkillManifest(
                name="test", instructions="Use tool X for research."
            ),
            functions=[],
        )
        reg._skills["test"] = s

        combined = reg.get_instructions_for_skills(["test"])
        assert "Use tool X for research." in combined

        def instructions(context_variables):
            return f"You are an agent.\n\n{combined}"

        agent = Agent(name="Test", instructions=instructions)
        prompt = agent.instructions({})
        assert "Use tool X for research." in prompt
