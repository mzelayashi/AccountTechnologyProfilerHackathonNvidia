"""People Resources skill — find the right SHI engineer / vendor for an engagement.

Backed by the CSV resource directory (`atlas.store.people`). The brain routes natural-language asks
("I need an expert in TOLA who can do PAM or EDR") here; the in-app People Resources view uses the
same `people.search()` for its live filter. Search is deterministic (instant, offline) — no Copilot
round-trip needed to find people.
"""
from __future__ import annotations

from atlas.skills.base import Field, Skill, SkillResult, register


def _fmt(rows: list[dict], limit: int = 15) -> str:
    if not rows:
        return ("**No matching resource found.** Try a broader term (a region like *TOLA* or a skill "
                "like *EDR*, *PAM*, *SD-WAN*), or browse **Skills → People Resources**.")
    out = [f"Found **{len(rows)}** matching resource(s) — top {min(limit, len(rows))}:\n",
           "| Name | Practice | Region | Skills | Manager | SHI/Ext |",
           "|---|---|---|---|---|---|"]
    for r in rows[:limit]:
        skills = (r.get("specialty") or "").replace("|", "/")[:70]
        out.append(f"| {r.get('name','')} | {r.get('practice','')} | {r.get('region','') or '—'} "
                   f"| {skills or '—'} | {r.get('manager','') or '—'} | {r.get('org','')} |")
    return "\n".join(out)


@register
class FindResource(Skill):
    key = "find_resource"
    name = "People Resources"
    icon = "🧑‍💼"
    description = ("Find the right SHI engineer or vendor for an engagement — by region, skill, or "
                   "practice (e.g. \"a TOLA expert who can do PAM or EDR\"). Browse/edit the full "
                   "directory in Skills → People Resources.")
    inputs = [Field("need", "What you need",
                    "e.g. an expert in TOLA who can do PAM or EDR")]

    def run(self, ctx, ask, log) -> SkillResult:
        from atlas.store import people
        need = (ctx.get("need") or ctx.get("question") or ctx.get("account") or "").strip()
        if not need:
            return SkillResult(text="Tell me what you need — a region, a skill, or a practice "
                                    "(e.g. *TOLA EDR* or *PAM expert in the Southeast*).")
        log(f"🔎 Searching the resource directory for: {need}")
        rows = people.search(need=need)
        log(f"   {len(rows)} match(es).")
        return SkillResult(text=_fmt(rows), data={"need": need, "matches": rows[:25]})
