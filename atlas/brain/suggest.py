"""Continual Suggestions — the proactive "next best action" advisor on the Home screen.

Two tiers:
  • Tier 1 (instant, free): rule-based suggestions from local state — the next meeting, its customer,
    recent activity, time of day. No Copilot call. Computed fresh on every poll.
  • Tier 2 (strategic, throttled): a Copilot-Web pass that reads the next meeting + that customer's
    saved data and proposes specific plays. Runs as a `suggest` job, cached here, refreshed only when
    the context changes or the frequency floor elapses.

Everything here only *suggests* a command the user can tap — it never runs anything itself.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re

import config

_CACHE = config.VAULT_DIR / "brain" / "suggestions.json"
_MAX = 4


# ---------------- signals ----------------
def _next_meeting() -> dict | None:
    """The next upcoming meeting: the earliest not-yet-past meeting today, else tomorrow's first."""
    try:
        from atlas.artifacts import dashboard_html
        from atlas.skills.daily_briefing import load_for
    except Exception:
        return None
    today = datetime.date.today().isoformat()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    for date_str, kind in ((today, "today"), (tomorrow, "tomorrow")):
        cards = load_for(date_str)
        if not cards:
            continue
        items = dashboard_html.enrich(cards, day_kind=kind)
        upcoming = [m for m in items if not m.get("past") and (m.get("title") or "").strip()]
        if upcoming:
            m = upcoming[0]
            return {"title": m["title"], "time": m.get("time", ""), "date": date_str, "when": kind}
    return None


def _customer_of(title: str) -> tuple[str, bool]:
    """(name, is_known) — derive a customer from a meeting title and snap to a vault customer if we have one."""
    try:
        from atlas.brain.brainwave import resolve_customer
        from atlas.skills.trip_report import _derive_customer
        raw = (_derive_customer(title) or "").strip()
        canon = resolve_customer(raw) if raw else None
        return (canon or raw, bool(canon))
    except Exception:
        return ("", False)


def _has_atp(customer: str) -> bool:
    try:
        from atlas.atp import data_library
        return bool(data_library.load(customer))
    except Exception:
        return False


def _recent_customer() -> str:
    """The customer of the most recent filed trip-report artifact (for a follow-up nudge)."""
    try:
        from atlas.store import artifacts
        for r in artifacts.list_summaries(limit=8):
            if r.get("skill") == "trip_report" and (r.get("customer") or "").strip():
                return r["customer"].strip()
    except Exception:
        pass
    return ""


# ---------------- tier 1 (instant) ----------------
def _mk(label: str, command: str, source: str = "instant") -> dict:
    sid = "s" + hashlib.md5((source + "|" + command).encode("utf-8")).hexdigest()[:10]
    return {"id": sid, "label": label, "command": command, "source": source}


def instant(s: dict) -> list[dict]:
    """Tier-1 rule-based suggestions — instant, no Copilot. `s` = the settings dict."""
    out: list[dict] = []
    focus = (s.get("suggestions_focus_customer") or "").strip()
    nm = _next_meeting()

    # 1) the next meeting and its customer
    if nm:
        cust, known = _customer_of(nm["title"])
        who = focus or cust
        when = "today" if nm["when"] == "today" else "tomorrow"
        out.append(_mk(f"Prep me for {('the ' + who) if who else 'your next'} meeting ({when}"
                       + (f" {nm['time']}" if nm.get("time") else "") + ")",
                       f"meeting prep for {who}" if who else f"prep for my next meeting: {nm['title']}"))
        if who:
            out.append(_mk(f"Strategic briefing for {who}", f"strategic briefing for {who}"))

    # 2) the focused customer (if pinned) — deeper plays
    if focus:
        out.append(_mk(f"Battlecard for {focus}", f"battlecard for {focus}"))
        out.append(_mk(f"Whitespace opportunities for {focus}", f"whitespace for {focus}"))

    # 3) a recent meeting's customer → follow up
    rc = _recent_customer()
    if rc and rc != focus:
        out.append(_mk(f"Draft a follow-up for {rc}", f"follow up with {rc}"))

    # 4) morning → daily briefing
    if datetime.datetime.now().hour < 11:
        out.append(_mk("Create today's daily briefing", "create today's daily briefing"))

    # de-dupe by id, keep order, cap
    seen, uniq = set(), []
    for it in out:
        if it["id"] not in seen:
            seen.add(it["id"])
            uniq.append(it)
    return uniq


# ---------------- tier 2 context + cache ----------------
def context_key(s: dict) -> str:
    """A short string of the Tier-2-relevant context. When it changes, Tier-2 should recompute."""
    focus = (s.get("suggestions_focus_customer") or "").strip()
    if focus:
        return f"focus:{focus.lower()}"
    nm = _next_meeting()
    return f"meeting:{(nm['title'] if nm else '').lower()}|{nm['date'] if nm else ''}"


def load_cache() -> dict:
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8")) if _CACHE.exists() else {}
    except Exception:
        return {}


def save_cache(context: str, items: list[dict]) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"context": context, "ts": _now_iso(), "items": items},
                                     indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def cache_is_stale(s: dict, cache: dict) -> bool:
    """True if Tier-2 should refresh: context changed OR older than the frequency floor."""
    if cache.get("context") != context_key(s):
        return True
    try:
        ts = datetime.datetime.fromisoformat(cache.get("ts", ""))
    except Exception:
        return True
    floor = int(s.get("suggestions_frequency_min") or 60)
    return (datetime.datetime.now() - ts).total_seconds() >= floor * 60


def in_workhours(s: dict) -> bool:
    if not s.get("suggestions_workhours_only", True):
        return True
    return 7 <= datetime.datetime.now().hour < 19


# ---------------- tier 2 (AI) prompt + parse ----------------
def ai_target(s: dict) -> tuple[str, dict | None]:
    """(customer, meeting) the AI tier should advise on — the focus customer, else the next meeting's."""
    focus = (s.get("suggestions_focus_customer") or "").strip()
    nm = _next_meeting()
    if focus:
        return focus, nm
    if nm:
        cust, _ = _customer_of(nm["title"])
        return cust, nm
    return "", None


def ai_prompt(customer: str, meeting: dict | None, saved_text: str) -> str:
    ctx = (f"My next meeting is \"{meeting['title']}\" ({meeting.get('when','')} "
           f"{meeting.get('time','')}).\n" if meeting else "")
    data = (saved_text or "").strip()[:8000] or "(no saved notes on file for this customer yet.)"
    return (
        f"You advise an SHI Solutions Architect. {ctx}"
        f"Customer in focus: {customer or '(unknown)'}.\n\n"
        f"Based ONLY on what is below, propose UP TO 3 concrete next actions I could take right now to "
        f"prepare. Each action must map to one of these ATLAS skills: meeting_prep, strategic_briefing, "
        f"battlecard, whitespace, account_360, follow_up, environment_topology — OR a product research "
        f"question. Return EXACTLY one per line, formatted as:\n"
        f"LABEL :: COMMAND\n"
        f"where LABEL is a SPECIFIC, self-explanatory button label of ~3-6 words that names the subject "
        f"(customer / product / topic) — e.g. \"BeyondTrust vs Delinea battlecard\", NOT a vague label "
        f"like \"Vendor Comparison\" — and COMMAND is the plain-English instruction I'd type "
        f"(e.g. \"battlecard for {customer}\" or \"is CrowdStrike a good fit for {customer}\"). No other "
        f"text, no numbering.\n\n=== {customer} — SAVED NOTES ===\n{data}")


def parse_ai(answer: str, customer: str) -> list[dict]:
    items: list[dict] = []
    for ln in (answer or "").splitlines():
        ln = re.sub(r"^[\s\-*•\d.]+", "", ln).strip()
        if "::" not in ln:
            continue
        label, _, command = ln.partition("::")
        label, command = label.strip().strip('"'), command.strip().strip('"')
        if 3 < len(label) < 60 and 3 < len(command) < 140:
            items.append(_mk(label, command, source="ai"))
        if len(items) >= 3:
            break
    return items


# ---------------- the merged panel ----------------
def _fresh(cache: dict, hours: int = 6) -> bool:
    """True if the cache was written within the last `hours` — used to DISPLAY cached suggestions.
    (Context drift, e.g. the next meeting changing as the calendar gathers, must NOT hide them.)"""
    try:
        ts = datetime.datetime.fromisoformat(cache.get("ts", ""))
    except Exception:
        return False
    return (datetime.datetime.now() - ts).total_seconds() <= hours * 3600


def panel(s: dict) -> list[dict]:
    """Tier-1 (fresh, rule-based) + Tier-2 (cached, recent) merged, capped — the list the API serves.
    Cached AI items show whenever they're recent; `context_key` only governs when they REFRESH, never
    whether they display (otherwise a context shift at startup would silently hide them)."""
    items = list(instant(s))
    cache = load_cache()
    if _fresh(cache):
        for it in (cache.get("items") or []):
            items.append(it)
    seen, uniq = set(), []
    for it in items:
        if it.get("id") and it["id"] not in seen and it.get("command"):
            seen.add(it["id"])
            uniq.append(it)
    return uniq[:_MAX]
