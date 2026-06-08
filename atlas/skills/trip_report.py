"""Trip Report — generate a structured report from a meeting's Teams transcript via Copilot."""
from __future__ import annotations

import datetime
import html
import re

import config
from atlas.store import vault

from .base import Field, Skill, SkillResult, register

# The verbatim Trip Report prompt (Copilot replaces the old Mindspark call).
TRIP_REPORT_PROMPT = """For this call transcribe from the conversation between multiple parties \
including customer vendor and their purpose for their end-users/customers select, deploy and \
manage technology to solve business and technology challenges and achieve their goals. and you \
will write a full analysis contains the following elements formatted, and no hyperlinks. Make \
sure to remove all links including hyperlinks or footnotes:

Summary:
 •

Agenda:
 •

Opps Identified & BANTC
 • B:
 • A:
 • N:
 • T:
 • C:

Initiatives:

Tech Profile Updates:

Meeting Notes:

Environment:

Detailed Discussion:

Technical Notes:

ROLES:

Potential Next steps:

Please make sure that if multiple Opportunities are identified they are each listed separately \
with their own BANTC analysis. For the Initiatives section, identify if it is Security or Storage \
or both. For the Summary section at the top, make it detailed and break down all business aspects \
of the call. For Potential Next steps, identify who said what and to whom to derive action items \
where other meetings can be set up around that action item, and list who is involved on each \
action item. For the Technical Notes section, add all granular specific notes about everything \
discussed on a specific level — technical questions, configurations, and any technical snippets \
that may be needed later to assess the scenarios and solutions presented. Under the ROLES section, \
show each participant's name and their title/role description and company. \
NO FOOTNOTES, NO CITATIONS WHATSOEVER, and REMOVE ALL HYPERLINKS and system-mandated markers in \
the output response."""


def _prefix(title: str, date: str) -> str:
    return (
        f"Base this entirely on the Microsoft Teams meeting transcript for my meeting titled "
        f"'{title}'{f' on {date}' if date else ''}. You have access to the transcript for Teams "
        f"calls. Start your reply directly with the 'Summary' section — do NOT add any preamble, "
        f"disclaimer, or note about transcripts being unavailable or the analysis being "
        f"reconstructed, and do not repeat the meeting title inside the sections. Then:\n\n"
    )


# Title words that are clearly the meeting TOPIC, not the customer.
_TOPIC_WORDS = re.compile(
    r"\b(meeting|sync|discussion|review|call|intro|introduction|networking|demo|qbr|abr|"
    r"planning|kickoff|kick-?off|standup|stand-?up|follow.?up|connect|brief(ing)?|workshop|"
    r"session|recap|catch.?up|monthly|weekly|biweekly|quarterly|annual|q[1-4]|business|"
    r"technical|deep dive|onboarding|training|proposal|sow)\b", re.I)

_SECTIONS = ("summary", "agenda", "opps identified", "opportunities identified", "initiatives",
             "tech profile", "meeting notes", "environment", "detailed discussion",
             "technical notes", "roles", "potential next", "next steps")


def _derive_customer(title: str) -> str:
    parts = [p.strip() for p in re.split(r"[|+]", title) if p.strip()]
    cands = [p for p in parts if p.lower() not in ("shi", "shi inc") and not _TOPIC_WORDS.search(p)]
    if cands:
        return cands[-1]
    nonshi = [p for p in parts if p.lower() != "shi"]
    return (max(nonshi, key=len) if nonshi else title).strip()


def _derive_topic(title: str, customer: str) -> str:
    parts = [p.strip() for p in re.split(r"\|", title) if p.strip()]
    keep = [p for p in parts if p.lower() != "shi"
            and customer.lower() not in p.lower() and p.lower() not in customer.lower()]
    topic = " | ".join(keep) if keep else title
    topic = re.sub(r"\bSHI\b", "", topic).replace("+", " ").strip(" |").strip()
    return re.sub(r"\s{2,}", " ", topic) or "Meeting"


def _fmt_date(date: str):
    try:
        dt = datetime.date.fromisoformat(date)
    except Exception:
        dt = datetime.date.today()
    return dt.strftime("%m/%d/%Y"), dt.isoformat()


def _from_summary(report: str) -> str:
    """Drop anything Copilot put before the first section header (preamble/echoed title)."""
    lines = report.splitlines()
    for i, ln in enumerate(lines):
        low = ln.strip().lower().rstrip(":")
        if any(low == s or low.startswith(s) for s in _SECTIONS):
            return "\n".join(lines[i:]).strip()
    return report.strip()


def _header(customer: str, ae: str, topic: str, disp_date: str) -> str:
    return (
        f"Trip Report | {topic} | {customer}\n\n"
        f"Customer: {customer}\n"
        f"AE: {ae}\n"
        f"Topic: {topic}\n"
        f"Meeting Date {disp_date}\n\n"
        f"*Internal notes – Please read and edit before sending externally*\n\n"
    )


def _norm(s: str) -> str:
    """Normalize a line for title-comparison (unescape, drop separators/punctuation, lowercase)."""
    s = html.unescape(s)
    s = re.sub(r"[|/\-–—:*#>•\s]+", " ", s)
    return s.strip().lower()


def _dedupe_title(report: str, title: str) -> str:
    """Remove standalone lines that are just the meeting title echoed (Copilot repeats it a lot),
    and collapse runs of blank lines."""
    tnorm = _norm(title)
    out, blanks = [], 0
    for i, line in enumerate(report.splitlines()):
        if i > 0 and tnorm and _norm(line) == tnorm:  # keep an optional title at the very top
            continue
        if not line.strip():
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        out.append(line)
    return "\n".join(out).strip()


@register
class TripReport(Skill):
    key = "trip_report"
    name = "Trip Report"
    icon = "🧾"
    description = "Structured trip report from a meeting's Teams transcript (Summary/BANTC/etc)."
    inputs = [
        Field("meeting", "Meeting (title)", "e.g. SHI | AWC Inc | Monthly Sync"),
        Field("date", "Date (optional)", "", required=False),
    ]

    def run(self, ctx, ask, log) -> SkillResult:
        title = (ctx.get("meeting") or "").strip()
        if not title:
            return SkillResult(text="Enter a meeting title.")
        date = (ctx.get("date") or "").strip()
        disp_date, file_date = _fmt_date(date)
        log(f"Generating trip report for '{title}' from its transcript…")
        report = ask(_prefix(title, date) + TRIP_REPORT_PROMPT)
        if not report:
            return SkillResult(text="No report captured — it's visible in the Copilot window.")
        body = _from_summary(_dedupe_title(report, title))   # Summary…Next Steps only
        customer = (ctx.get("customer") or "").strip() or _derive_customer(title)
        ae = (ctx.get("ae") or ctx.get("organizer") or "").strip()
        topic = _derive_topic(title, customer)
        full = _header(customer, ae, topic, disp_date) + body + "\n"
        path = vault.write_text(
            config.EXPORTS_DIR / "trip_reports" / f"{file_date}_{vault.slug(title)}.md", full)
        return SkillResult(text=full, files=[path])
