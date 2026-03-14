"""SkillRegistry extends the existing Registry to track loaded skills."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from research_agent.inno.registry import Registry, registry
from research_agent.inno.skills.base import Skill, SkillManifest
from research_agent.inno.skills.loader import SkillLoader


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
        return cls._instance

    @property
    def loader(self) -> SkillLoader:
        return self._loader

    def register_skill(self, skill: Skill) -> None:
        """Register a loaded skill and inject its tools into the base registry."""
        self._skills[skill.name] = skill
        for func in skill.functions:
            self._base_registry._registry["tools"][func.__name__] = func

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
                self._base_registry._registry["tools"].pop(func.__name__, None)


skill_registry = SkillRegistry()
