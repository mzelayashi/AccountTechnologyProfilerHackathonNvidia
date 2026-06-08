"""A4 prompt-based skills for a solutions engineer (Copilot-powered, saved to the vault)."""
from __future__ import annotations

from .base import Field, PromptSkill, register


@register
class MeetingPrep(PromptSkill):
    key = "meeting_prep"
    name = "Meeting Prep"
    icon = "📋"
    description = "Deep prep for one meeting: attendees, history, talking points, your role."
    inputs = [Field("account", "Account / customer", "e.g. ProPetro"),
              Field("meeting", "Meeting (title or topic)", "e.g. NVIDIA Live Demo")]
    save_subdir = "meetings"
    save_name = "prep.md"
    prompt_template = (
        "Prepare me for my upcoming meeting '{meeting}' with {account}. Using the latest context "
        "from recent meetings and emails, give: (1) attendees and their roles, (2) where we left off, "
        "(3) the likely agenda, (4) my role and goals, (5) 5 specific talking points, (6) likely "
        "objections and how to handle them, (7) what to bring/prepare. Be specific and cite recent events."
    )


@register
class Account360(PromptSkill):
    key = "account_360"
    name = "Account 360"
    icon = "🛰"
    description = "One-page snapshot: initiatives, stakeholders, tech stack, opportunities, risks."
    inputs = [Field("account", "Account / customer", "e.g. AWC Inc")]
    save_name = "account_360.md"
    prompt_template = (
        "Give me a concise one-page Account 360 for {account} based on recent meetings and emails: "
        "current initiatives, key stakeholders (names + roles), known technology stack, open "
        "opportunities, active risks, and our current engagement status. Use clear headed sections."
    )


@register
class FollowUp(PromptSkill):
    key = "follow_up"
    name = "Follow-Up Composer"
    icon = "✉️"
    description = "Action items + a ready-to-send recap email from the latest meeting."
    inputs = [Field("account", "Account / customer", "e.g. Broadway Bank")]
    save_subdir = "meetings"
    save_name = "followup.md"
    prompt_template = (
        "From my most recent meeting with {account}, produce: (1) a bulleted list of action items "
        "with owners and due dates, and (2) a concise, professional recap email I can send to the "
        "customer summarizing decisions, next steps, and timing. Keep the email ready to paste."
    )


@register
class Whitespace(PromptSkill):
    key = "whitespace"
    name = "Whitespace Radar"
    icon = "📡"
    description = "Upsell/cross-sell opportunities for the account, with evidence."
    inputs = [Field("account", "Account / customer", "e.g. ProPetro")]
    save_name = "whitespace.md"
    prompt_template = (
        "Identify upsell and cross-sell whitespace for {account} based on recent meetings and emails. "
        "For each opportunity give: the gap/need, the SHI solution that fits, supporting evidence "
        "(meeting/date/stakeholder), rough priority, and the next step to advance it."
    )


@register
class Battlecard(PromptSkill):
    key = "battlecard"
    name = "Competitive Battlecard"
    icon = "⚔️"
    description = "Competitors in play, our advantages/vulnerabilities, objection handling."
    inputs = [Field("account", "Account / customer", "e.g. AmeriVet")]
    save_name = "battlecard.md"
    prompt_template = (
        "Build a competitive battlecard for {account} based on recent meetings and emails: which "
        "competitors are in play, our advantages, our vulnerabilities, the customer's evaluation "
        "criteria, and recommended positioning + objection-handling for each competitor."
    )
