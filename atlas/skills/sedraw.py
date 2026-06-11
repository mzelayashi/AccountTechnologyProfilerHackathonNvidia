"""SE Draw diagram skills — registered so they appear as cards in the Skills gallery.

Their cards are special-cased in the front-end (index.html) to open bespoke browsable views
(showSEDrawNetwork / showSEDrawVision) — like the People Resources skill — rather than the
generic input form. Generation runs synchronously via dedicated Api methods (atlas/web/api.py
-> atlas/sedraw/service.py), so run() below is only a harmless fallback if ever invoked as a job.
"""
from atlas.skills.base import Skill, SkillResult, register

_HINT = "Open this skill from the Skills page, pick a customer, then generate the diagram."


@register
class SEDrawNetwork(Skill):
    key = "sedraw_network"
    name = "SEdraw Network Diagrams"
    icon = "🛰"
    description = "Multi-site network topology diagram for a customer, from their Excel intake."
    inputs = []

    def run(self, ctx, ask, log) -> SkillResult:  # fallback only; UI uses the custom view
        return SkillResult(text=_HINT)


@register
class SEDrawVision(Skill):
    key = "sedraw_vision"
    name = "SEdraw Vision Boards"
    icon = "🧭"
    description = "Technology Vision Board (current/future state) for a customer, from their Excel."
    inputs = []

    def run(self, ctx, ask, log) -> SkillResult:  # fallback only; UI uses the custom view
        return SkillResult(text=_HINT)
