"""Natural-language command router for the Jarvis command box.

Maps a free-text request to one or more job specs ({kind, ctx, title}) using a fast local
intent map (keyword → skill) plus light entity/date extraction — no extra Copilot round-trip.
Anything it can't classify falls back to a free-form "Ask Copilot" job, so the box always
does something useful. Routing can be upgraded to a Copilot-classified intent later.
"""
from __future__ import annotations

import datetime
import re

_QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{2,})[\"'“”‘’]")
# A run of Capitalized / ALLCAPS tokens after a preposition — usually the account/customer.
_PREP = re.compile(
    r"\b(?:for|of|with|about|from|on)\s+([A-Z0-9][\w&./-]*(?:\s+[A-Z0-9][\w&./-]*){0,4})")
_CAPRUN = re.compile(r"([A-Z][\w&./-]*(?:\s+[A-Z][\w&./-]*){0,4})")
_STOP = {"i", "a", "the", "my", "me", "create", "make", "do", "an", "customer", "meeting",
         "report", "analysis", "briefing", "please", "give", "get", "from", "for"}


def _entity(text: str) -> str:
    m = _QUOTED.search(text)
    if m:
        return m.group(1).strip()
    m = _PREP.search(text)
    if m:
        cand = m.group(1).strip().rstrip(".,!?")
        if cand.lower() not in _STOP:
            return cand
    # Longest run of capitalized words anywhere (e.g. "Dental Depot", "AWC").
    best = ""
    for m in _CAPRUN.finditer(text):
        c = m.group(1).strip()
        if c.lower() not in _STOP and len(c) > len(best):
            best = c
    return best


def _date_kind(low: str) -> str | None:
    for k in ("yesterday", "tomorrow", "today"):
        if k in low:
            return k
    return None


def _iso(kind: str | None) -> str:
    if not kind:
        return ""
    off = {"yesterday": -1, "tomorrow": 1}.get(kind, 0)
    return (datetime.date.today() + datetime.timedelta(days=off)).isoformat()


def route(text: str) -> list[dict]:
    t = (text or "").strip()
    if not t:
        return []
    low = t.lower()
    ent = _entity(t)
    who = ent or "?"

    def spec(kind, ctx, title):
        return {"kind": kind, "ctx": ctx, "title": title}

    if "trip report" in low or ("trip" in low and "report" in low):
        return [spec("trip_report", {"meeting": ent, "date": _iso(_date_kind(low))},
                     f"Trip Report — {ent or 'meeting'}")]
    if "battlecard" in low or "competit" in low:
        return [spec("battlecard", {"account": ent}, f"Battlecard — {who}")]
    if "whitespace" in low or "upsell" in low or "cross-sell" in low or "cross sell" in low:
        return [spec("whitespace", {"account": ent}, f"Whitespace — {who}")]
    if "topology" in low or "environment" in low or "architecture" in low or "diagram" in low:
        return [spec("environment_topology", {"account": ent}, f"Environment — {who}")]
    if "account 360" in low or "snapshot" in low or "360" in low:
        return [spec("account_360", {"account": ent}, f"Account 360 — {who}")]
    if "follow" in low or "recap email" in low:
        return [spec("follow_up", {"account": ent}, f"Follow-Up — {who}")]
    if ("prep" in low or "prepare" in low) and "report" not in low:
        return [spec("meeting_prep", {"account": ent, "meeting": ent}, f"Meeting Prep — {who}")]
    if "knowledge" in low or "ingest" in low:
        return [spec("knowledge_drop", {"account": ent}, f"Knowledge Drop — {who}")]
    if ("strategic" in low or "briefing" in low or "analy" in low or "brief" in low):
        return [spec("strategic_briefing", {"account": ent}, f"Strategic Briefing — {who}")]
    # Fallback: ask Copilot directly.
    return [spec("ask", {"question": t}, t[:60])]
