"""SkillRegistry extends the existing Registry to track loaded skills."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from research_agent.inno.registry import Registry, registry
from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.agent_card import AgentCard, build_agent_card
from research_agent.inno.skills.events import SkillEvent, skill_event_bus
from research_agent.inno.skills.loader import SkillLoader
from research_agent.inno.skills.search import ToolSearchIndex, ToolSearchResult


class SkillRegistry:
    """Singleton that bridges skills with the existing Registry.

    This composes with (not replaces) the existing Registry singleton.
    Tools registered via @register_tool continue to work unchanged.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: Dict[str, Skill] = {}
            cls._instance._loader = SkillLoader()
            cls._instance._base_registry = registry
            cls._instance._search_index: Optional[ToolSearchIndex] = None
            cls._instance._tool_stacks: Dict[str, List[Tuple[Optional[str], Callable]]] = {}
        return cls._instance

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    def register_skill(self, skill: Skill) -> None:
        """Register a loaded skill and inject its tools into the base registry."""
        self._skills[skill.name] = skill
        for func in skill.functions:
            tool_name = func.__name__
            stack = self._tool_stacks.setdefault(tool_name, [])
            if not stack:
                existing = self._base_registry._registry["tools"].get(tool_name)
                if existing is not None:
                    stack.append((None, existing))
            stack.append((skill.name, func))
            self._base_registry._registry["tools"][tool_name] = func
        skill_event_bus.publish(
            SkillEvent(
                event_type="loaded",
                skill_name=skill.name,
                manifest=skill.manifest,
            )
        )

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def get_skill_tools(self, skill_name: str) -> List[Callable]:
        """Get all tool functions for a named skill."""
        skill = self._skills.get(skill_name)
        if skill is None:
            return []
        return list(skill.functions)

    def list_skills(self) -> List[str]:
        """Return names of all registered (loaded) skills."""
        return list(self._skills.keys())

    def list_available(self) -> List[str]:
        """Return names of all discoverable skills (loaded or not)."""
        return self._loader.list_available()

    def load_and_register(self, skill_name: str, **kwargs) -> Skill:
        """Load a skill via the loader and register it."""
        skill = self._loader.load(skill_name, **kwargs)
        self.register_skill(skill)
        return skill

    def get_instructions_for_skills(self, skill_names: List[str]) -> str:
        """Compose instruction fragments from multiple skills."""
        parts = []
        for name in skill_names:
            skill = self._skills.get(name)
            if skill and skill.instructions:
                parts.append(f"## Skill: {skill.name}\n{skill.instructions}")
        return "\n\n".join(parts)

    def unload_skill(self, name: str) -> None:
        """Unload a skill and remove its tools from the base registry."""
        skill = self._skills.pop(name, None)
        if skill:
            for func in skill.functions:
                tool_name = func.__name__
                stack = self._tool_stacks.get(tool_name, [])
                stack = [entry for entry in stack if entry[0] != name]
                if stack:
                    self._tool_stacks[tool_name] = stack
                    self._base_registry._registry["tools"][tool_name] = stack[-1][1]
                else:
                    self._tool_stacks.pop(tool_name, None)
                    self._base_registry._registry["tools"].pop(tool_name, None)
            skill_event_bus.publish(
                SkillEvent(
                    event_type="unloaded",
                    skill_name=name,
                    manifest=skill.manifest,
                )
            )

    # --- Tool Search ---

    def build_search_index(self) -> None:
        """Build the embedding-based tool search index from all scanned manifests."""
        if self._search_index is None:
            self._search_index = ToolSearchIndex()
        manifests = self._loader.scan()
        self._search_index.build_index(manifests)

    def search_tools(
        self, query: str, top_k: int = 5
    ) -> List[ToolSearchResult]:
        """Search for tools by natural language query (lazy index build)."""
        if self._search_index is None:
            self.build_search_index()
        return self._search_index.search(query, top_k=top_k)

    # --- A2A Agent Card ---

    def to_agent_card(
        self,
        name: str = "AI-Researcher",
        url: str = "",
        description: str = "",
    ) -> AgentCard:
        """Export an A2A-compatible Agent Card from registered skills."""
        return build_agent_card(self, name=name, url=url, description=description)


skill_registry = SkillRegistry()
