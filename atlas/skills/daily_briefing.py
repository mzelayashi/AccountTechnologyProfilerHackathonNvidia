"""Daily Briefing — today's meetings + per-meeting prep, as clickable cards."""
from __future__ import annotations

import datetime
import json
import re

import config
from atlas.store import vault

from .base import Skill, SkillResult, register

# Copilot's RELATIVE date anchor ("today"/"tomorrow") is non-deterministic for this
# calendar — the same meetings flip between "today" and "tomorrow" across runs. We pin each
# grounding turn to an ABSOLUTE date so Copilot filters by an explicit day with no drift.
def _long_date(d: datetime.date) -> str:
    # Windows strftime has no %-d, so build the day number by hand.
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"


# ONE gentle, conversational prompt. Rigid/imperative phrasing ("output ONLY… EXACTLY this…")
# trips Copilot's guardrail ("I can't chat about this"); a polite request with a *suggested*
# label style grounds reliably and parses via the separator-agnostic label-walker below.
def _day_prompt(d: datetime.date) -> str:
    today = datetime.date.today()
    note = ("a short recap of what was discussed and any decisions" if d < today
            else "a short prep with the latest context, the agenda, and my role" if d > today
            else "a short recap if it already happened, otherwise a short prep")
    return (f"Please list all of my meetings for {_long_date(d)}, and add {note} for each one. "
            f"Put each meeting on its own line like this — TITLE: meeting title | TIME: start - end | "
            f"ORG: organizer | NOTE: the recap or prep. "
            f"If I had no meetings that day, just reply: No meetings scheduled.")


def _day_prompt_plain(d: datetime.date) -> str:
    return (f"Please list all of my meetings for {_long_date(d)} and add a short recap "
            f"(or prep, if it hasn't happened yet) for each.")


# Walk the field labels themselves — each TITLE: begins a new meeting — so parsing does NOT
# depend on Copilot's separators (it variously uses ' :: ', newlines, or '---', inconsistently).
_LBL = re.compile(r"\b(TITLE|TIME|ORG|NOTE)\s*:\s*", re.IGNORECASE)


def _clean_val(v: str) -> str:
    return re.sub(r"[\s:|*\-]+$", "", v.strip()).strip().strip("<>").strip()


def _norm(s: str) -> str:
    import html as _h
    return re.sub(r"[^a-z0-9]+", " ", _h.unescape(s or "").lower()).strip()


def _strip_echoed_title(note: str, title: str) -> str:
    """Copilot appends the bare meeting title on its own line after each NOTE — drop those so the
    recap reads cleanly (and the card preview shows the recap, not the title)."""
    t = _norm(title)
    keep = [ln for ln in note.splitlines() if not (t and _norm(ln) == t)]
    return "\n".join(keep).strip()


def _parse_delimited(text: str) -> list[dict]:
    """Parse the 'TITLE: .. TIME: .. ORG: .. NOTE: ..' reformat by label-walking (separator-
    agnostic). Each TITLE starts a meeting; later labels fill it. Rebuilds the Time:/Organizer:
    body the dashboard's enrich()/_meta() expect."""
    text = html.unescape(text)
    marks = list(_LBL.finditer(text))
    if not marks:
        return []
    cards: list[dict] = []
    cur: dict | None = None
    for i, m in enumerate(marks):
        label = m.group(1).upper()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        val = _clean_val(text[m.end():end])
        if label == "TITLE":
            cur = {"title": val, "time": "", "org": "", "note": ""}
            cards.append(cur)
        elif cur is not None:
            cur[{"TIME": "time", "ORG": "org", "NOTE": "note"}[label]] = val
    out = []
    for c in cards:
        if not c["title"]:
            continue
        note = _strip_echoed_title(c["note"], c["title"])
        body = f"Time: {c['time']}\nOrganizer: {c['org']}\n{note}".strip()
        out.append({"title": c["title"], "body": body})
    return out


def _date_for(day: str) -> str:
    days = {"tomorrow": 1, "yesterday": -1}
    return (datetime.date.today() + datetime.timedelta(days=days.get(day, 0))).isoformat()

import html

# Every meeting block contains a "Time:" line — the one anchor across all Copilot formats.
_TIME_LINE = re.compile(r"^\s*Time:\s*\d", re.IGNORECASE)
_NUM = re.compile(r"^\s*(\d{1,2})\.\s+(\S.*)$")  # fallback delimiter
# Trailing wrap-up / global sections that aren't a single meeting.
_FOOTER = re.compile(
    r"(⚠️?\s*Scheduling Conflict|Bottom Line|✅?\s*Summary of Key|^\s*Sources\s*$|If you want)",
    re.IGNORECASE | re.MULTILINE,
)
_CONFLICTS = re.compile(
    r"(⚠️?\s*Scheduling Conflict.*?)(?:Bottom Line|✅?\s*Summary of Key|\nSources|If you want|$)",
    re.IGNORECASE | re.DOTALL,
)


def _trim_body(body: str) -> str:
    m = _FOOTER.search(body)
    if m:
        body = body[: m.start()]
    return body.strip()


def split_meetings(text: str) -> list[dict]:
    text = html.unescape(text)  # &#124; -> |
    lines = text.splitlines()
    cards: list[dict] = []

    # Primary: anchor on every "Time:" line; the title is the non-blank line above it.
    time_idx = [i for i, ln in enumerate(lines) if _TIME_LINE.match(ln)]
    if time_idx:
        starts = []
        for ti in time_idx:
            j = ti - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            starts.append((max(j, 0), ti))
        for k, (title_i, _ti) in enumerate(starts):
            end = starts[k + 1][0] if k + 1 < len(starts) else len(lines)
            cards.append({"title": lines[title_i].strip(),
                          "body": "\n".join(lines[title_i + 1:end]).strip()})
        # strip the next meeting's title that bleeds onto the end of each body
        for k in range(len(cards) - 1):
            nt = cards[k + 1]["title"]
            bl = cards[k]["body"].split("\n")
            while bl and bl[-1].strip() == nt:
                bl.pop()
            cards[k]["body"] = "\n".join(bl).strip()
        if cards:
            cards[-1]["body"] = _trim_body(cards[-1]["body"])

    # Fallback: numbered list "1. Title".
    if not cards:
        cur = None
        for line in lines:
            m = _NUM.match(line)
            if m and len(m.group(2).strip()) > 3:
                if cur:
                    cards.append(cur)
                cur = {"title": m.group(2).strip(), "body": ""}
            elif cur is not None:
                cur["body"] += line + "\n"
        if cur:
            cards.append(cur)
        cards = [{"title": c["title"], "body": _trim_body(c["body"])} for c in cards]

    # Append the scheduling-conflicts section as its own card, if present.
    cm = _CONFLICTS.search(text)
    if cm and cm.group(1).strip():
        cards.append({"title": "⚠️ Scheduling Conflicts", "body": cm.group(1).strip()})

    return cards or [{"title": "Today's briefing", "body": text.strip()}]


def load_for(date_str: str) -> list[dict] | None:
    p = config.DAILY_DIR / date_str / "briefing.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("meetings")
        except Exception:
            return None
    return None


def load_today() -> list[dict] | None:
    return load_for(datetime.date.today().isoformat())


def _as_date(date) -> datetime.date:
    if isinstance(date, datetime.date):
        return date
    return datetime.date.fromisoformat(str(date))


# Copilot sometimes refuses/cannot ground in the calendar ("I can't access your calendar…") and then
# echoes the format template — which must NEVER be mistaken for a real meeting.
_NO_ACCESS = re.compile(
    r"can'?t\s+(directly\s+)?access|cannot\s+access|don'?t\s+have\s+access|do\s+not\s+have\s+access|"
    r"not\s+able\s+to\s+(list|access|retrieve|see)|unable\s+to\s+(list|access|retrieve|see)|"
    r"paste\s+your\s+calendar|provide\s+your\s+calendar|share\s+your\s+calendar|"
    r"without\s+the\s+schedule\s+being\s+provided|no\s+access\s+to\s+your\s+(calendar|microsoft)",
    re.I)
_PLACEHOLDER_TITLES = {"meeting title", "title", "organizer", "start end", "none", "note"}


def _is_no_access(answer: str) -> bool:
    return bool(_NO_ACCESS.search(answer or ""))


def _drop_placeholders(cards: list[dict]) -> list[dict]:
    """Remove cards that are just the echoed format template (e.g. title 'meeting title'), so a refusal
    can never become a bogus meeting."""
    out = []
    for c in cards:
        t = (c.get("title") or "").strip()
        if not t or _norm(t) in _PLACEHOLDER_TITLES:
            continue
        body = (c.get("body") or "").lower()
        if "start - end" in body and "organizer" in body and len(body) < 140:  # template body
            continue
        out.append(c)
    return out


def gather_day(ask_chain, date, log=print) -> list[dict]:
    """Gather ONE day by ABSOLUTE date on one Copilot session with a single gentle prompt
    (retrying once with an even plainer prompt if Copilot refuses/returns nothing), then parse
    → cache vault/daily/<date>/briefing.json. Returns the parsed meeting cards.

    Designed to be a job body so yesterday/today/tomorrow each run on their own Chrome instance."""
    d = _as_date(date)
    date_str = d.isoformat()
    answer = ask_chain([_day_prompt(d)])

    # Empty OR a calendar-refusal ("I can't access your calendar…") → one plainer retry.
    if not answer or len(answer.strip()) < 12 or _is_no_access(answer):
        log(f"Gather for {date_str} was empty or blocked — retrying with a simpler prompt.")
        answer = ask_chain([_day_prompt_plain(d)])

    if not answer or len(answer.strip()) < 12:
        log(f"Gather for {date_str} looked empty — keeping the previous briefing.")
        return load_for(date_str) or []

    # If Copilot still refused calendar access, do NOT let the echoed template become a bogus meeting.
    if _is_no_access(answer):
        log(f"⚠️ Couldn't read the calendar for {date_str} — tap ↻ Refresh to retry.")
        return load_for(date_str) or []

    cards = _drop_placeholders(_parse_delimited(answer) or split_meetings(answer))

    # Only write REAL parsed meetings (after the template/placeholder filter) or an explicit empty day —
    # never a refusal/echoed template, which would otherwise clobber a good cached briefing.
    has_meetings = bool(cards)
    says_none = "no meeting" in answer.lower()
    if not has_meetings and not says_none:
        log(f"Gather for {date_str} returned no real meeting data — keeping the previous briefing.")
        return load_for(date_str) or []

    today = datetime.date.today()
    rel = "yesterday" if d < today else "tomorrow" if d > today else "today"
    vault.write_json(vault.daily_dir(date_str) / "briefing.json",
                     {"date": date_str, "day": rel, "raw": answer, "meetings": cards})
    log(f"Parsed {len(cards)} meeting(s) for {date_str}.")
    return cards


@register
class DailyBriefing(Skill):
    key = "daily_briefing"
    name = "Daily Briefing"
    icon = "🌅"
    description = "Today's meetings with per-meeting prep — your morning brief."
    inputs = []

    def run(self, ctx, ask, log) -> SkillResult:
        # `ask` is a single-prompt callable; use slot 0's chain runner for the multi-turn gather.
        from atlas.engine import get_engine
        day = (ctx or {}).get("day", "today")
        date = _date_for(day)
        cards = gather_day(lambda prompts: get_engine().ask_chain(prompts, on_log=log), date, log)
        if not cards:
            return SkillResult(text="Couldn't gather a briefing this time (kept the last good one). Try ↻ Refresh.",
                               cards=load_for(date) or [])
        return SkillResult(text=f"{len(cards)} meeting(s) for {day}.", cards=cards)
