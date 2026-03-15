"""A2A Agent Card export from SkillRegistry."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from research_agent.inno.skills.registry import SkillRegistry


class AgentCapability(BaseModel):
    """A single capability advertised in the Agent Card."""

    name: str
    description: str = ""
    tools: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class AgentCard(BaseModel):
    """A2A-compatible Agent Card describing this agent's capabilities."""

    name: str
    description: str = ""
    url: str = ""
    version: str = "0.1.0"
    capabilities: List[AgentCapability] = Field(default_factory=list)
    authentication: Optional[dict] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=2, exclude_none=True)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return self.model_dump(exclude_none=True)


def build_agent_card(
    registry: "SkillRegistry",
    name: str = "AI-Researcher",
    url: str = "",
    description: str = "",
) -> AgentCard:
    """Build an AgentCard from all registered skills in the registry."""
    capabilities: List[AgentCapability] = []
    for skill_name in registry.list_skills():
        skill = registry.get_skill(skill_name)
        if skill is None:
            continue
        capabilities.append(
            AgentCapability(
                name=skill.name,
                description=skill.manifest.description,
                tools=skill.manifest.tools,
                tags=skill.manifest.tags,
            )
        )
    return AgentCard(
        name=name,
        description=description,
        url=url,
        capabilities=capabilities,
    )
