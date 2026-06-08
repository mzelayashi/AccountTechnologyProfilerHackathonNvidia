"""Skill abstraction + registry.

A skill = prompt(s) to the Copilot engine → parse → write vault artifacts → SkillResult.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Field:
    key: str
    label: str
    placeholder: str = ""
    required: bool = True


@dataclass
class SkillResult:
    text: str = ""                      # markdown answer for the result pane
    data: object = None                 # parsed structured data, if any
    files: list[Path] = field(default_factory=list)
    diagram_html: Path | None = None    # diagram to open in browser
    cards: list[dict] | None = None     # e.g. [{"title","body"}] for briefings


# ask(prompt) -> answer ; on_log(msg) -> None
Ask = Callable[[str], str]
Log = Callable[[str], None]


class Skill(ABC):
    key: str = ""
    name: str = ""
    icon: str = "•"
    description: str = ""
    inputs: list[Field] = []

    @abstractmethod
    def run(self, ctx: dict, ask: Ask, log: Log) -> SkillResult:
        ...


class PromptSkill(Skill):
    """Convenience base: one Copilot prompt → markdown answer saved to the account folder."""

    prompt_template: str = ""   # may reference {account} and other input keys
    save_subdir: str = "."      # relative to the account dir
    save_name: str = "output.md"

    def build_prompt(self, ctx: dict) -> str:
        try:
            return self.prompt_template.format(**{k: (v or "") for k, v in ctx.items()})
        except (KeyError, IndexError):
            return self.prompt_template

    def run(self, ctx: dict, ask: Ask, log: Log) -> SkillResult:
        import datetime

        from atlas.store import vault

        account = (ctx.get("account") or "").strip()
        answer = ask(self.build_prompt(ctx))
        files = []
        if account and answer:
            p = (vault.account_dir(account) / self.save_subdir /
                 f"{datetime.date.today().isoformat()}_{self.save_name}")
            files = [vault.write_text(p, answer)]
        return SkillResult(text=answer or "(no answer captured — see the Copilot window)", files=files)


_REGISTRY: dict[str, Skill] = {}


def register(cls):
    """Class decorator: instantiate and register a skill."""
    inst = cls()
    _REGISTRY[inst.key] = inst
    return cls


def all_skills() -> list[Skill]:
    return list(_REGISTRY.values())


def get_skill(key: str) -> Skill | None:
    return _REGISTRY.get(key)
