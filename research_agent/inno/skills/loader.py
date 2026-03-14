"""Discovers and loads skills from the filesystem."""

from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from research_agent.inno.skills.base import Skill, SkillDependency, SkillManifest
from research_agent.inno.skills.errors import SkillLoadError, SkillNotFoundError

logger = logging.getLogger(__name__)


class SkillLoader:
    """Discovers skills from filesystem directories and loads them on demand.

    Two-phase design:
        scan()  -- reads SKILL.md manifests only (no Python imports)
        load()  -- imports the skill module and resolves tool functions
    """

    def __init__(self, skill_dirs: Optional[List[str]] = None):
        if skill_dirs is None:
            skill_dirs = [str(Path(__file__).parent)]
        self.skill_dirs = [Path(d) for d in skill_dirs]
        self._manifests: Dict[str, SkillManifest] = {}
        self._skills: Dict[str, Skill] = {}

    def scan(self) -> Dict[str, SkillManifest]:
        """Walk skill directories and parse all SKILL.md files.

        Returns dict of {skill_name: SkillManifest}.
        Does NOT import Python modules.
        """
        self._manifests.clear()
        for base_dir in self.skill_dirs:
            if not base_dir.exists():
                continue
            for skill_dir in sorted(base_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    manifest = self._parse_skill_md(skill_md)
                    manifest.source_path = str(skill_dir)
                    self._manifests[manifest.name] = manifest
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", skill_md, e)
        return self._manifests

    def load(self, skill_name: str, **kwargs) -> Skill:
        """Fully load a skill: import its Python module and resolve tools.

        Args:
            skill_name: Name of the skill to load.
            **kwargs: Environment objects (code_env, file_env, etc.) to
                      inject into tools that require them.

        Raises:
            SkillNotFoundError: If no manifest found for skill_name.
            SkillLoadError: If Python module import fails.
        """
        if skill_name in self._skills:
            return self._skills[skill_name]

        if skill_name not in self._manifests:
            self.scan()
        if skill_name not in self._manifests:
            raise SkillNotFoundError(f"Skill '{skill_name}' not found")

        manifest = self._manifests[skill_name]

        # Load dependencies first
        for dep in manifest.dependencies:
            if dep.skill_name not in self._skills:
                if dep.optional:
                    try:
                        self.load(dep.skill_name, **kwargs)
                    except (SkillNotFoundError, SkillLoadError):
                        pass
                else:
                    self.load(dep.skill_name, **kwargs)

        # Import the skill's Python module
        skill_dir = Path(manifest.source_path)
        module_path = self._dir_to_module_path(skill_dir)

        try:
            module = importlib.import_module(module_path)
        except Exception as e:
            raise SkillLoadError(
                f"Failed to import skill '{skill_name}' from {module_path}: {e}"
            ) from e

        if not hasattr(module, "get_tools"):
            raise SkillLoadError(
                f"Skill '{skill_name}' module has no get_tools() function"
            )

        functions = module.get_tools(**kwargs)

        skill = Skill(manifest=manifest, functions=functions)
        self._skills[skill_name] = skill
        logger.info("Loaded skill '%s' with tools: %s", skill_name, skill.tool_names)
        return skill

    def load_many(self, skill_names: List[str], **kwargs) -> List[Skill]:
        """Load multiple skills."""
        return [self.load(name, **kwargs) for name in skill_names]

    def get_manifest(self, skill_name: str) -> Optional[SkillManifest]:
        """Return manifest for a skill (scan first if needed)."""
        if not self._manifests:
            self.scan()
        return self._manifests.get(skill_name)

    def list_available(self) -> List[str]:
        """Return names of all discovered skills."""
        if not self._manifests:
            self.scan()
        return list(self._manifests.keys())

    def _parse_skill_md(self, path: Path) -> SkillManifest:
        """Parse a SKILL.md file into a SkillManifest."""
        content = path.read_text(encoding="utf-8")
        sections = self._split_sections(content)

        name = sections.get("name", path.parent.name).strip()
        version = sections.get("version", "0.1.0").strip()
        description = sections.get("description", "").strip()
        author = sections.get("author", "").strip()

        tools = self._parse_list(sections.get("tools", ""))
        required_config = self._parse_list(sections.get("required_config", ""))
        tags = self._parse_list(sections.get("tags", ""))

        deps_raw = self._parse_list(sections.get("dependencies", ""))
        dependencies = []
        for d in deps_raw:
            optional = d.endswith("(optional)")
            dep_name = d.replace("(optional)", "").strip()
            dependencies.append(
                SkillDependency(skill_name=dep_name, optional=optional)
            )

        instructions = sections.get("instructions", "").strip()

        return SkillManifest(
            name=name,
            version=version,
            description=description,
            author=author,
            tools=tools,
            dependencies=dependencies,
            required_config=required_config,
            instructions=instructions,
            tags=tags,
        )

    def _split_sections(self, content: str) -> Dict[str, str]:
        """Split SKILL.md content into sections keyed by ## heading."""
        sections: Dict[str, str] = {}
        current_key = "preamble"
        current_lines: list = []

        for line in content.split("\n"):
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                if current_lines:
                    sections[current_key] = "\n".join(current_lines).strip()
                current_key = (
                    heading_match.group(1).strip().lower().replace(" ", "_")
                )
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections[current_key] = "\n".join(current_lines).strip()

        return sections

    @staticmethod
    def _parse_list(text: str) -> List[str]:
        """Parse markdown list items (lines starting with '- ')."""
        return [
            line.lstrip("- ").strip()
            for line in text.split("\n")
            if line.strip().startswith("- ")
        ]

    def _dir_to_module_path(self, skill_dir: Path) -> str:
        """Convert a skill directory path to a Python module import path."""
        parts = skill_dir.parts
        try:
            ra_idx = parts.index("research_agent")
            return ".".join(parts[ra_idx:])
        except ValueError:
            raise SkillLoadError(
                f"Cannot determine module path for {skill_dir}"
            )
