"""Core data models for the Skill system."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class SkillDependency(BaseModel):
    """Declares a dependency on another skill."""

    skill_name: str
    optional: bool = False


class SkillManifest(BaseModel):
    """Parsed representation of a SKILL.md file."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    tools: List[str] = Field(default_factory=list)
    tool_schemas: Dict[str, dict] = Field(default_factory=dict)
    dependencies: List[SkillDependency] = Field(default_factory=list)
    required_config: List[str] = Field(default_factory=list)
    instructions: str = ""
    tags: List[str] = Field(default_factory=list)
    source_path: Optional[str] = None


class Skill(BaseModel):
    """A loaded, ready-to-use skill with callable tool functions."""

    manifest: SkillManifest
    functions: List[Callable] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def tool_names(self) -> List[str]:
        return [f.__name__ for f in self.functions]

    @property
    def instructions(self) -> str:
        return self.manifest.instructions

    def get_tool(self, name: str) -> Optional[Callable]:
        """Return a specific tool function by name."""
        for f in self.functions:
            if f.__name__ == name:
                return f
        return None

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Return JSON Schema for a tool, from manifest or function signature."""
        if tool_name in self.manifest.tool_schemas:
            return self.manifest.tool_schemas[tool_name]
        func = self.get_tool(tool_name)
        if func is not None:
            from research_agent.inno.util import function_to_json

            schema = function_to_json(func)
            return schema["function"]["parameters"]
        return None
