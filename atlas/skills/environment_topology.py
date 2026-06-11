"""Environment Topology — map a customer's tech stack to a draw.io topology diagram."""
from __future__ import annotations

from atlas.artifacts import diagram_view, drawio
from atlas.store import vault

from .base import Field, Skill, SkillResult, register

# Line format is far more robust than JSON here — Copilot can't echo it into garbage.
_PROMPT = (
    "Based on recent meetings, emails, and documents for {account}, list the customer's known "
    "technology environment — only REAL products you have evidence for. Output ONE technology per "
    "line, no header and no extra commentary, in EXACTLY this pipe format:\n"
    "Vendor | Product | Category | Status\n"
    "Category must be one of: datacenter, networking, security, cloud, endpoint, data. "
    "Status must be one of: active, pilot, planned, evaluation, legacy.\n"
    "Example line:  VMware | vSphere | datacenter | active\n"
    "If you have no environment data for this account, reply with exactly: NO DATA"
)
_CATS = {"datacenter", "networking", "security", "cloud", "endpoint", "data", "other"}
_STATUSES = {"active", "pilot", "planned", "evaluation", "legacy"}


def _parse(answer: str) -> list[dict]:
    techs = []
    for line in answer.splitlines():
        if line.count("|") < 3:
            continue
        v, p, c, s = (x.strip() for x in line.split("|")[:4])
        if v.lower() == "vendor" or not (v or p):
            continue
        cat = c.lower() if c.lower() in _CATS else "other"
        st = s.lower() if s.lower() in _STATUSES else ""
        techs.append({"vendor": v, "product": p, "category": cat, "status": st})
    return techs


def _md(techs, account):
    cats: dict[str, list[dict]] = {}
    for t in techs:
        cats.setdefault(t["category"].title(), []).append(t)
    out = [f"# {account} — Technology Environment", ""]
    for cat, items in cats.items():
        out.append(f"## {cat}")
        for t in items:
            out.append(f"- {t['vendor']} {t['product']}".rstrip()
                       + (f"  _({t['status']})_" if t["status"] else ""))
        out.append("")
    return "\n".join(out)


@register
class EnvironmentTopology(Skill):
    key = "environment_topology"
    name = "Environment Topology"
    icon = "🗺"
    description = "Map the customer's tech environment to a draw.io topology diagram."
    inputs = [Field("account", "Account / customer", "e.g. AWC Inc")]

    def run(self, ctx, ask, log) -> SkillResult:
        account = (ctx.get("account") or "").strip()
        if not account:
            return SkillResult(text="Enter an account name.")
        log(f"Mapping {account}'s technology environment on Nemotron…")
        answer = ask(_PROMPT.format(account=account))
        techs = _parse(answer)
        if not techs:
            return SkillResult(
                text=f"No technology environment data found for **{account}**.\n\n"
                f"Model output:\n\n{answer}")

        log(f"Building topology from {len(techs)} technologies…")
        xml = drawio.topology(techs, account)
        adir = vault.account_dir(account)
        dpath = vault.write_text(adir / "diagrams" / "topology.drawio", xml)
        html = diagram_view.write_viewer(xml, adir / "diagrams" / "topology.html",
                                         f"{account} — Topology")
        return SkillResult(text=_md(techs, account), data=techs, files=[dpath, html],
                           diagram_html=html)
