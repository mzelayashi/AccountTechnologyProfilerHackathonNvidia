"""P1 of the ATLAS Brain — a manifest-grounded router.

Instead of keyword matching, ATLAS asks Copilot (Web mode — fast, no tenant needed) to classify a
free-text request against the **capability manifest** and decide one of:
  - run_skill  → which built-in skill + extracted inputs to run
  - settings   → it's a settings change ATLAS can't make itself; point the user where to go
  - cannot_do  → no capability fits; explain why and recommend a skill to add

This is the first real piece of the Brain: capability-aware intent. The planner / sub-agent fan-out
(brainwaves) build on top of this in later phases. See ATLAS_ARCHITECTURE.md.
"""
from __future__ import annotations

import re

from atlas.brain import capabilities
from atlas.engine.extract import extract_json

# Fast-path: meta-questions about ATLAS ITSELF are answered from the manifest (no Copilot round-trip).
_META_RE = re.compile(
    r"\b(what|which|list|show|tell me).{0,40}\b(can|do|are)\b.{0,30}\b(you|atlas|your)\b"
    r"|what are (your|atlas|the) (skills|capabilities|abilities|features)"
    r"|what can (you|atlas) (do|help)|^help\b|your (skills|capabilities)|atlas (skills|capabilities)",
    re.I)


def is_meta(text: str) -> bool:
    return bool(_META_RE.search((text or "").strip()))


# Fast-path: "trip report(s) for all/every/each of <day>'s meetings" → the trip_reports_day workflow
# (one trip_report skill run per meeting of that day → N artifacts), for yesterday / today / tomorrow.
_TRT_RE = re.compile(
    r"trip\s*report.{0,40}\b(all|every|each|both)\b.{0,40}\bmeeting",
    re.I)
_DAY_RE = re.compile(r"\b(yesterday|today's|todays|today|tomorrow|this day|the day|that day)\b", re.I)


def meeting_trip_reports_day(text: str) -> str | None:
    """Deterministic fast-path for 'trip reports for all/each of <day>'s meetings' — but ONLY when an
    EXPLICIT relative day word is present (yesterday / today / tomorrow / this·the·that day). Returns
    that day, else None. When no explicit day word is found we return None ON PURPOSE so the request
    falls through to the LLM brain — which can understand date ranges ("May 21 to June 5"), specific
    dates, and relative spans. (Previously this defaulted to 'today', silently swallowing ranges.)"""
    t = (text or "").strip()
    if not _TRT_RE.search(t):
        return None
    m = _DAY_RE.search(t)
    if not m:
        return None
    w = m.group(1).lower()
    if w.startswith("yesterday"):
        return "yesterday"
    if w.startswith("tomorrow"):
        return "tomorrow"
    return "today"


def is_trip_reports_today(text: str) -> bool:   # back-compat
    return meeting_trip_reports_day(text) == "today"


def json_ok(text: str) -> bool:
    """Accept predicate for the engine: a parseable JSON object = a finished decision."""
    d = extract_json(text or "")
    return isinstance(d, dict) and bool(d)


def _skill_lines() -> str:
    lines = []
    for c in capabilities.manifest():
        if c["kind"] == "skill":
            inp = ", ".join(c["inputs"]) or "(none)"
            lines.append(f'  - key="{c["id"]}" — {c["description"]} | inputs: {inp}')
    return "\n".join(lines)


def _settings_lines() -> str:
    return "\n".join(
        f'  - "{c["title"]}" → {c["settings_location"]}'
        for c in capabilities.manifest() if c["kind"] == "settings-pointer")


def _planned_lines() -> str:
    return "\n".join(
        f'  - "{c["title"]}" — {c["description"]}\n      recommend: {c["recommend"]}'
        for c in capabilities.manifest() if c["kind"] == "planned")


def _today_iso() -> str:
    import datetime
    return datetime.date.today().isoformat()


def _prompt(text: str) -> str:
    return f"""You are ATLAS's routing brain. Decide how to handle the user's request using ONLY the
capabilities below. Do not invent skills.

TODAY'S DATE is {_today_iso()} (ISO, YYYY-MM-DD). Use this to resolve ANY time expression in the
request — "May 21 to June 5", "last two weeks", "yesterday", a specific date — into ABSOLUTE ISO
dates. NEVER rely on the model's own sense of "today"; anchor every date to the value above.

BUILT-IN SKILLS you can run (pick the single best fit; fill its inputs from the request):
{_skill_lines()}

SETTINGS ATLAS CANNOT change itself (if the request is to change one of these, you must POINT the
user — ATLAS cannot modify its own settings):
{_settings_lines()}

PLANNED capabilities that DO NOT EXIST YET (if the request specifically needs one of these — e.g. it
mentions an uploaded Excel/intake file — you MUST return action=cannot_do with the recommendation
below; do NOT force-fit a different skill):
{_planned_lines()}

BRAINWAVE (deep multi-agent analysis): when the user wants to EVALUATE or RESEARCH a specific
product/technology FOR a named customer — "is X a good fit for <customer>", "should <customer> use
X", "research X for <customer>", "would X work for <customer>" — choose action=brainwave. ATLAS will
research the product (Web) AND analyze that customer's real environment (Work + filed profile) in
parallel, then synthesize a grounded verdict. This is much better than a plain ask for fit questions.

PLAN (decompose multi-target goals): each skill operates on a SINGLE target — one account, one
meeting. If the user wants a skill applied to MULTIPLE targets, you MUST think about HOW: run that one
skill once per target, in parallel. Choose action=plan with the per-item "skill" and ONE of:
  • "items": ["Acme", "Globex", ...]  — when the targets are NAMED in the request (several customers,
    several meetings), OR
  • "collection": one of  yesterday_meetings | today_meetings | tomorrow_meetings | customers |
    date_range  — when the targets are a set ATLAS must look up.
For a SKILL applied to MEETINGS OVER A SPAN OF DATES, use collection=date_range and ALSO fill
"range": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}} with ABSOLUTE dates resolved from TODAY'S DATE
above. ANY skill works here, not just trip reports — set "skill" to whatever the user asked for
(trip_report, strategic_briefing, battlecard, meeting_prep, …); ATLAS gathers the meetings in that
range and applies the skill at its natural granularity (per meeting, or once per distinct customer for
account-level skills). If the user wants only external customer meetings (skipping internal syncs,
1:1s, lunch, admin/focus blocks, OOO), set "filter": "external_customer".
Examples:
  "battlecards for AWC, ProPetro and Sendero" → plan{{skill:battlecard, items:[AWC,ProPetro,Sendero]}};
  "trip reports for each of yesterday's meetings" → plan{{skill:trip_report, collection:yesterday_meetings}};
  "trip report for all my meetings from May 21 to June 5, external customers only" →
    plan{{skill:trip_report, collection:date_range, range:{{start:2026-05-21, end:2026-06-05}},
    filter:external_customer}};
  "strategic briefings for any external customer calls from May 21 to June 5" →
    plan{{skill:strategic_briefing, collection:date_range, range:{{start:2026-05-21, end:2026-06-05}},
    filter:external_customer}}  (→ one briefing per distinct customer).
Do NOT collapse a multi-target request into a single run_skill.

USER REQUEST:
\"\"\"{text}\"\"\"

If the user asks about ATLAS ITSELF — what it can do, its skills/capabilities/features, "what can
you do", "help" — choose action=capabilities (ATLAS answers from its own manifest; do NOT route a
meta-question to Copilot).

Reply with ONLY a JSON object (no code fences), shaped exactly:
{{
  "action": "run_skill" | "plan" | "brainwave" | "capabilities" | "settings" | "cannot_do",
  "skill": "<one of the skill keys above, or empty>",
  "ctx": {{ "<input key>": "<value>" }},
  "items": ["<target>", "..."],
  "collection": "yesterday_meetings | today_meetings | tomorrow_meetings | customers | date_range | ",
  "range": {{ "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" }},
  "filter": "external_customer | ",
  "title": "<short job title>",
  "explanation": "<one or two sentences: what you will do, or why you can't>",
  "settings_location": "<for action=settings: exactly where the user must go>",
  "recommendation": "<for action=cannot_do: the specific new skill to add and what it would produce>"
}}

Rules:
- A skill applied to MULTIPLE targets → action=plan with "skill" + either "items" (named) or
  "collection" (a set to resolve). NEVER collapse multiple targets into one run_skill.
- Meetings across a DATE SPAN → action=plan, collection=date_range, with "range" (absolute ISO dates
  from TODAY) and optionally filter=external_customer. Resolve all dates against TODAY'S DATE above.
- Product/technology FIT or RESEARCH for a named customer → action=brainwave, ctx={{"product":
  "<the product/technology>", "customer": "<the customer name>"}}.
- A plain question or anything conversational → action=run_skill, skill="ask", ctx={{"question": <the full request>}}.
- If it maps to a skill, set action=run_skill, the skill key, and ctx with that skill's input keys
  only (e.g. account/customer name, meeting).
- If it's asking to change a setting listed above → action=settings with settings_location.
- If it needs a PLANNED capability (e.g. an uploaded Excel/intake file) → action=cannot_do with the recommendation.
- If no capability fits → action=cannot_do with a concrete recommendation."""


def classify(ask_web, text: str, on_log=print) -> dict:
    """`ask_web(prompt)->answer` must run Copilot in WEB mode with accept=json_ok. Returns the
    decision dict (falls back to a plain 'ask' decision if classification fails)."""
    text = (text or "").strip()
    if not text:
        return {}
    on_log("🧠 Classifying the request against ATLAS capabilities…")
    raw = ask_web(_prompt(text))
    d = extract_json(raw)
    if not isinstance(d, dict) or not d.get("action"):
        on_log("🧠 Classifier unclear — treating as a general question.")
        return {"action": "run_skill", "skill": "ask", "ctx": {"question": text},
                "title": text[:50], "explanation": "Answering as a general question."}
    # sanitize: only allow known skill keys
    valid = {c["id"] for c in capabilities.manifest() if c["kind"] == "skill"}
    if d.get("action") == "run_skill" and d.get("skill") not in valid:
        d["skill"] = "ask"
        d["ctx"] = {"question": text}
    if not isinstance(d.get("ctx"), dict):
        d["ctx"] = {}
    on_log(f"🧠 Decision: {d.get('action')}" + (f" → {d.get('skill')}" if d.get("skill") else ""))
    return d
