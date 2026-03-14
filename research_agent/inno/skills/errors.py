"""Skill-system specific exceptions."""


class SkillError(Exception):
    """Base exception for skill-related errors."""


class SkillNotFoundError(SkillError):
    """Raised when a requested skill cannot be found on disk."""


class SkillLoadError(SkillError):
    """Raised when a skill's Python module fails to import or initialize."""


class SkillDependencyError(SkillError):
    """Raised when a required skill dependency cannot be satisfied."""
