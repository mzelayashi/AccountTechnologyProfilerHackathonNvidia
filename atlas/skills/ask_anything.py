"""Free-form: ask Copilot anything (grounded in the signed-in user's M365 data)."""
from __future__ import annotations

from .base import Field, Skill, SkillResult, register


@register
class AskAnything(Skill):
    key = "ask"
    name = "Ask Copilot"
    icon = "🟣"
    description = "Ask any question — Copilot answers from your meetings, emails, and files."
    inputs = [Field("question", "Your question",
                    "e.g. tell me about the current initiatives for AWC from the last meetings")]

    def run(self, ctx, ask, log) -> SkillResult:
        question = (ctx.get("question") or "").strip()
        if not question:
            return SkillResult(text="(no question entered)")
        answer = ask(question)
        return SkillResult(text=answer or "(no answer captured — see the Copilot window)")
