"""Skill registry. Importing a skill module registers it."""
from . import (  # noqa: F401  (register on import)
    ask_anything,
    daily_briefing,
    environment_topology,
    knowledge_drop,
    more_skills,
    peopleresources,
    sedraw,
    strategic_briefing,
    trip_report,
)
from .base import Skill, SkillResult, Field, all_skills, get_skill, register  # noqa: F401

__all__ = ["Skill", "SkillResult", "Field", "all_skills", "get_skill", "register"]
