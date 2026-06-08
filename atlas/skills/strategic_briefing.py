"""Strategic Account Briefing — ATPtool's intelligence briefing, powered by Copilot.

Asks Copilot for a structured JSON synthesis of the account's recent meetings/emails,
renders a readable briefing, and generates a decision-tree .drawio + diagrams.net viewer.
"""
from __future__ import annotations

import datetime

import config
from atlas.artifacts import diagram_view, drawio
from atlas.engine.extract import extract_json
from atlas.store import vault

from .base import Field, Skill, SkillResult, register

_SCHEMA = (
    "Respond with ONLY a JSON object (no prose, no code fences) filled with REAL, specific data "
    "for this account. Do NOT return placeholders or copy these descriptions. The object must have "
    "these keys:\n"
    "- executive_summary: string (2-4 sentences naming people, technologies, and a date)\n"
    "- current_initiatives: array of {project, status, details, our_involvement, next_milestone}\n"
    "- strategic_opportunities: array of {opportunity, priority, estimated_value, "
    "recommended_approach, next_step, win_probability}\n"
    "- decision_tree: object {central_question, branches: array of "
    "{path, likelihood (high|medium|low), our_position, leads_to: array of strings}}\n"
    "- immediate_next_steps: array of {action, owner, timing}\n"
    "- risks_to_monitor: array of {risk, severity (high|medium|low), mitigation}\n"
    "- talking_points: array of {topic, point}\n"
    "If you have no data for this account, reply with exactly: NO DATA"
)


def _prompt(account: str) -> str:
    return (
        f"You are assisting a solutions engineer at SHI preparing for the account '{account}'. "
        f"Based on the last ~4 meetings/trip reports and recent emails for {account}, produce a "
        f"strategic intelligence briefing. Be specific and cite evidence (people, dates). "
        f"{_SCHEMA}"
    )


def _md(data: dict, account: str) -> str:
    out = [f"# Strategic Briefing — {account}", ""]
    if data.get("executive_summary"):
        out += ["## Executive summary", data["executive_summary"], ""]
    inits = data.get("current_initiatives") or []
    if inits:
        out.append("## Current initiatives")
        for i in inits:
            out.append(f"- **{i.get('project','')}** ({i.get('status','')}) — {i.get('details','')}")
            if i.get("next_milestone"):
                out.append(f"  ↳ next: {i['next_milestone']}")
        out.append("")
    opps = data.get("strategic_opportunities") or []
    if opps:
        out.append("## Strategic opportunities")
        for o in opps:
            out.append(f"- **{o.get('opportunity','')}** [{o.get('priority','')}, win {o.get('win_probability','')}]"
                       f" — {o.get('recommended_approach','')}")
            if o.get("next_step"):
                out.append(f"  ↳ next step: {o['next_step']}")
        out.append("")
    steps = data.get("immediate_next_steps") or []
    if steps:
        out.append("## Immediate next steps")
        for s in steps:
            out.append(f"- {s.get('action','')}  _( {s.get('owner','')} · {s.get('timing','')} )_")
        out.append("")
    risks = data.get("risks_to_monitor") or []
    if risks:
        out.append("## Risks to monitor")
        for r in risks:
            out.append(f"- [{r.get('severity','')}] {r.get('risk','')} — mitigation: {r.get('mitigation','')}")
        out.append("")
    tps = data.get("talking_points") or []
    if tps:
        out.append("## Talking points")
        for t in tps:
            out.append(f"- **{t.get('topic','')}**: {t.get('point','')}")
        out.append("")
    return "\n".join(out)


@register
class StrategicBriefing(Skill):
    key = "strategic_briefing"
    name = "Strategic Account Briefing"
    icon = "🎯"
    description = "Deep intelligence briefing for an account + decision-tree diagram."
    inputs = [Field("account", "Account / customer name", "e.g. AWC Inc")]

    def run(self, ctx, ask, log) -> SkillResult:
        account = (ctx.get("account") or "").strip()
        if not account:
            return SkillResult(text="Enter an account name.")
        log(f"Asking Copilot for a strategic briefing on {account}…")
        answer = ask(_prompt(account))
        if answer.strip().upper().startswith("NO DATA"):
            return SkillResult(text=f"Copilot has no briefing data for **{account}**.")
        data = extract_json(answer)
        if not isinstance(data, dict) or not (
            data.get("executive_summary") or data.get("current_initiatives")
        ):
            log("Copilot didn't return usable JSON — showing the raw answer.")
            return SkillResult(text=answer or "(no answer)")

        today = datetime.date.today().isoformat()
        adir = vault.account_dir(account)
        files = [
            vault.write_json(adir / "briefings" / f"{today}_strategic.json", data),
            vault.write_text(adir / "briefings" / f"{today}_strategic.md", _md(data, account)),
        ]

        diagram_html = None
        dt = data.get("decision_tree")
        if isinstance(dt, dict) and dt.get("branches"):
            log("Generating decision-tree diagram…")
            xml = drawio.decision_tree(dt)
            dpath = vault.write_text(adir / "diagrams" / "decision_tree.drawio", xml)
            files.append(dpath)
            diagram_html = diagram_view.write_viewer(
                xml, adir / "diagrams" / "decision_tree.html", f"{account} — Decision Tree")
            files.append(diagram_html)

        log("Done.")
        return SkillResult(text=_md(data, account), data=data, files=files, diagram_html=diagram_html)
