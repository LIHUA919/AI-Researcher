"""Skills subsystem for AI-Researcher.

Usage::

    from research_agent.inno.skills import skill_registry

    skill_registry.loader.scan()
    print(skill_registry.list_available())

    skill = skill_registry.load_and_register("arxiv_search")
    tools = skill_registry.get_skill_tools("arxiv_search")
"""

from research_agent.inno.skills.agent_card import AgentCapability, AgentCard
from research_agent.inno.skills.base import Skill, SkillDependency, SkillManifest
from research_agent.inno.skills.errors import (
    SkillDependencyError,
    SkillError,
    SkillLoadError,
    SkillNotFoundError,
)
from research_agent.inno.skills.events import SkillEvent, SkillEventBus, skill_event_bus
from research_agent.inno.skills.loader import SkillLoader
from research_agent.inno.skills.registry import SkillRegistry, skill_registry
from research_agent.inno.skills.search import ToolSearchIndex, ToolSearchResult

__all__ = [
    "AgentCapability",
    "AgentCard",
    "Skill",
    "SkillManifest",
    "SkillDependency",
    "SkillLoader",
    "SkillRegistry",
    "skill_registry",
    "SkillError",
    "SkillNotFoundError",
    "SkillLoadError",
    "SkillDependencyError",
    "SkillEvent",
    "SkillEventBus",
    "skill_event_bus",
    "ToolSearchIndex",
    "ToolSearchResult",
]
