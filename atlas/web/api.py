"""HTTP API for the WebView2 shell (PULL model — JS polls these methods).

Everything heavy runs as a background Job on the engine pool (see atlas/jobs), so work never
stops when the user navigates. The page polls jobs()/days()/artifacts() and renders state.
"""
from __future__ import annotations

import datetime

from atlas.artifacts import dashboard_html
from atlas.engine import get_pool
from atlas.jobs import get_manager
from atlas.skills import all_skills, get_skill
from atlas.skills.daily_briefing import load_for


def _greeting() -> str:
    import config
    h = datetime.datetime.now().hour
    part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
    return f"Good {part}"


def _today() -> str:
    return datetime.datetime.now().strftime("%A, %B %d, %Y")


def _date_for(kind: str) -> str:
    off = {"yesterday": -1, "tomorrow": 1}.get(kind, 0)
    return (datetime.date.today() + datetime.timedelta(days=off)).isoformat()


class Api:
    def __init__(self) -> None:
        self.window = None
        # The pool (and its profile cloning + Chrome workers) is built lazily on first use,
        # so constructing Api() never blocks the window from opening.

    @property
    def manager(self):
        return get_manager()

    # ---- metadata ----
    def skills(self) -> list[dict]:
        return [{
            "key": s.key, "name": s.name, "icon": s.icon, "description": s.description,
            "inputs": [{"key": f.key, "label": f.label, "placeholder": f.placeholder}
                       for f in s.inputs],
        } for s in all_skills()]

    def greeting(self) -> dict:
        return {"greeting": _greeting(), "date": _today()}

    def capabilities(self) -> list[dict]:
        """The capability manifest — everything ATLAS can/can't do (the Brain's introspection map)."""
        from atlas.brain import capabilities
        return capabilities.manifest()

    # ---- Continual Suggestions (the proactive next-best-action panel) ----
    def suggestions(self) -> dict:
        """Tier-1 (instant, fresh) + Tier-2 (cached, Copilot) suggestions for the Home panel. Also
        kicks off a throttled `suggest` job when the AI tier is due (context changed or stale)."""
        from atlas.brain import suggest as sg
        from atlas.store import settings
        s = settings.load()
        if not s.get("continual_suggestions", True):
            return {"enabled": False, "items": []}
        items = sg.panel(s)
        refreshing = self._suggest_running()   # true while any suggest job (auto OR manual) is in flight
        if s.get("suggestions_ai", True) and sg.in_workhours(s):
            cache = sg.load_cache()
            if sg.cache_is_stale(s, cache) and not refreshing:
                customer, meeting = sg.ai_target(s)
                if customer:
                    self.manager.submit("suggest",
                                        {"customer": customer, "meeting": meeting,
                                         "context": sg.context_key(s)},
                                        title="💡 Refreshing suggestions", icon="💡", mode="web")
                    refreshing = True
        return {"enabled": True, "items": items, "refreshing": refreshing}

    def _suggest_running(self) -> bool:
        try:
            return any(j.get("kind") == "suggest" and j.get("status") in ("queued", "waiting", "running")
                       for j in self.manager.list_jobs(limit=20))
        except Exception:
            return False

    def request_suggestions(self) -> dict:
        """Manual 'Suggest now' — force a Tier-2 run immediately, bypassing the frequency floor, the
        work-hours gate, and the AI toggle (an explicit tap is explicit intent). Shows on the loader."""
        from atlas.brain import suggest as sg
        from atlas.store import settings
        s = settings.load()
        if not s.get("continual_suggestions", True):
            return {"ok": False, "error": "Continual Suggestions is turned off in Settings."}
        customer, meeting = sg.ai_target(s)
        jid = self.manager.submit("suggest",
                                  {"customer": customer, "meeting": meeting,
                                   "context": sg.context_key(s), "manual": True},
                                  title="💡 Suggesting next steps…", icon="💡", mode="web")
        return {"ok": True, "job": jid}

    # ---- boot: gather yesterday + today + tomorrow as 3 parallel jobs ----
    def boot(self) -> dict:
        ids = {}
        for kind in ("yesterday", "today", "tomorrow"):
            date = _date_for(kind)
            label = {"yesterday": "Yesterday", "today": "Today", "tomorrow": "Tomorrow"}[kind]
            ids[kind] = self.manager.submit("gather_day", {"date": date},
                                            title=f"Gather {label}", icon="🗓")
        return {"ids": ids}

    def days(self) -> dict:
        """Enriched meeting cards per day, read live from each day's cache (fills as jobs finish)."""
        out = {}
        for kind in ("yesterday", "today", "tomorrow"):
            cards = load_for(_date_for(kind)) or []
            out[kind] = dashboard_html.enrich(cards, day_kind=kind)
        out["greeting"] = _greeting()
        out["date"] = _today()
        return out

    def refresh_day(self, kind: str = "today") -> dict:
        """Re-gather one day from Copilot (the ↻ Refresh button) — Copilot's calendar grounding is
        occasionally flaky, so this re-queries and overwrites that day if it grounds."""
        kind = kind if kind in ("yesterday", "today", "tomorrow") else "today"
        date = _date_for(kind)
        label = {"yesterday": "Yesterday", "today": "Today", "tomorrow": "Tomorrow"}[kind]
        jid = self.manager.submit("gather_day", {"date": date}, title=f"↻ Re-gather {label}", icon="🗓")
        return {"id": jid, "date": date}

    # ---- natural-language command box (the Brain) ----
    def command(self, text: str = "") -> dict:
        """Hand the request to the Brain (P1): a manifest-grounded router job classifies intent in
        Copilot Web, then runs the matched skill / points to a setting / explains what to add."""
        text = (text or "").strip()
        if not text:
            return {"ids": [], "routed": []}
        jid = self.manager.submit("brain_route", {"text": text},
                                  title=f"🧠 {text[:48]}", icon="🧠", mode="web")
        return {"ids": [jid], "routed": ["ATLAS is thinking…"]}

    # ---- skills (now jobs) ----
    def run_skill(self, key: str, ctx: dict | None = None) -> dict:
        sk = get_skill(key)
        ctx = ctx or {}
        title = (ctx.get("account") or ctx.get("meeting") or ctx.get("question")
                 or (sk.name if sk else key))
        jid = self.manager.submit(key, ctx, title=str(title)[:80])
        return {"id": jid}

    # ---- job tracking (top status bar) ----
    def jobs(self) -> list:
        return self.manager.list_jobs()

    def job(self, id: str = "") -> dict | None:
        return self.manager.get(id)

    def cancel_job(self, id: str = "") -> dict:
        """Stop an active job (the ✕ on a Working-on chip) and close the Chrome it's using."""
        return self.manager.cancel(id)

    def artifacts(self, limit: int = 0) -> list:
        """Lightweight, timestamp-sorted summaries (no full text). Full text loads via artifact()."""
        from atlas.store import artifacts
        return artifacts.list_summaries(limit=limit or None)

    def search_artifacts(self, q: str = "") -> list:
        """Search artifacts (incl. trip-report content) by title/customer/skill/text."""
        from atlas.store import artifacts
        return artifacts.list_summaries(query=q)

    def brainwaves(self) -> list:
        """Brainwave-history records (the agentic multi-agent outputs), newest first."""
        from atlas.store import artifacts
        return artifacts.list_brainwaves()

    def artifact(self, id: str = "") -> dict | None:
        from atlas.store import artifacts
        return artifacts.get(id)

    def delete_artifact(self, id: str = "", pin: str = "") -> dict:
        """Soft-delete an artifact (move its files to the recycle bin). PIN-guarded like customers."""
        from atlas.store import artifacts, settings
        saved = (settings.load().get("system_pin") or "").strip()
        if not saved:
            return {"ok": False, "error": "no_pin",
                    "message": "Set a 6-digit System PIN in Settings before deleting anything."}
        if (pin or "").strip() != saved:
            return {"ok": False, "error": "bad_pin", "message": "Incorrect System PIN."}
        return artifacts.delete(id)

    # ---- customer vault ----
    def customers(self) -> list:
        from atlas.store import customers
        return customers.list_customers()

    def create_customer(self, name: str = "") -> dict:
        from atlas.store import customers
        return customers.create_customer(name)

    def customer(self, name: str = "") -> dict:
        from atlas.store import customers
        return customers.detail(name)

    def assign_artifact(self, artifact_id: str = "", customer: str = "") -> dict:
        from atlas.store import customers
        return customers.assign_artifact(artifact_id, customer)

    def delete_customer(self, name: str = "", pin: str = "") -> dict:
        """Soft-delete a customer (move its folder to the recycle bin). Requires the System PIN set
        in Settings — a deliberate guard so nothing is deleted by accident."""
        from atlas.store import customers, settings
        saved = (settings.load().get("system_pin") or "").strip()
        if not saved:
            return {"ok": False, "error": "no_pin",
                    "message": "Set a 6-digit System PIN in Settings before deleting anything."}
        if (pin or "").strip() != saved:
            return {"ok": False, "error": "bad_pin", "message": "Incorrect System PIN."}
        return customers.delete_customer(name)

    # ---- People Resources (the SHI resource-alignment directory) ----
    @staticmethod
    def _pin_ok(pin: str) -> dict | None:
        """Shared System-PIN guard for People Resources writes. Returns an error dict on failure, or
        None when the PIN is valid (so the caller may proceed)."""
        from atlas.store import settings
        saved = (settings.load().get("system_pin") or "").strip()
        if not saved:
            return {"ok": False, "error": "no_pin",
                    "message": "Set a 6-digit System PIN in Settings before editing resources."}
        if (pin or "").strip() != saved:
            return {"ok": False, "error": "bad_pin", "message": "Incorrect System PIN."}
        return None

    def get_people(self) -> list:
        """The full resource directory, read fresh from the CSV (one-to-one mirror with disk)."""
        from atlas.store import people
        return people.load()

    def refresh_people(self) -> list:
        """Explicit reload button — same as get_people (the CSV is always read fresh)."""
        from atlas.store import people
        return people.load()

    def people_save(self, id: str = "", fields: dict | None = None, pin: str = "") -> dict:
        """PIN-gated edit of one resource; writes the CSV (the source of truth)."""
        err = self._pin_ok(pin)
        if err:
            return err
        from atlas.store import people
        rec = people.update(id, fields or {})
        return {"ok": True, "record": rec} if rec else {"ok": False, "error": "not_found"}

    def people_add(self, fields: dict | None = None, pin: str = "") -> dict:
        """PIN-gated add of a new resource."""
        err = self._pin_ok(pin)
        if err:
            return err
        from atlas.store import people
        f = fields or {}
        if not (f.get("name") or "").strip():
            return {"ok": False, "error": "name required"}
        return {"ok": True, "record": people.add(f)}

    def people_delete(self, id: str = "", pin: str = "") -> dict:
        """PIN-gated delete of a resource (recoverable — every import archives the full prior CSV)."""
        err = self._pin_ok(pin)
        if err:
            return err
        from atlas.store import people
        return {"ok": people.delete(id)}

    def people_import(self, pin: str = "", path: str = "") -> dict:
        """PIN-gated import: archive the current CSV, then load a new one (the newest CSV staged in
        the people-resources import/ folder, unless an explicit path is given)."""
        err = self._pin_ok(pin)
        if err:
            return err
        from atlas.store import people
        src = (path or "").strip() or people.newest_import()
        if not src:
            return {"ok": False, "error": "no_file",
                    "message": "Drop a .csv into the people-resources import/ folder first."}
        return people.import_csv(src)

    # ---- ATP technology profile + topology ----
    def atp_load(self, customer: str = "") -> dict:
        from atlas.atp import data_library
        return {"entries": data_library.load(customer),
                "statuses": list(data_library.DEPLOYMENT_STATUSES),
                "categories": list(data_library.CATEGORIES)}

    def atp_save(self, customer: str = "", entries: list | None = None) -> dict:
        from atlas.atp import data_library, recency, topology_html
        saved = data_library.save(customer, entries or [])
        recency.assign(customer, saved)          # refresh trip-report appearance counts
        saved = data_library.save(customer, saved)
        uri = topology_html.write(customer)      # re-render the diagram on every save
        return {"ok": True, "count": len(saved), "topology": uri,
                "html": topology_html.render(customer, saved)}

    def atp_topology(self, customer: str = "") -> dict:
        from atlas.atp import data_library, topology_html
        return {"uri": topology_html.write(customer),
                "html": topology_html.render(customer, data_library.load(customer))}

    def atp_generate(self, customer: str = "") -> dict:
        """Populate the profile from the customer's trip reports via Copilot WEB mode (a job)."""
        jid = self.manager.submit("atp_generate", {"customer": customer},
                                  title=f"ATP Profile — {customer}", icon="🛰", mode="web")
        return {"id": jid}

    def atp_profile(self, customer: str = "", generation: str = "") -> dict:
        """A customer profile snapshot: technologies + overview (3 paragraphs) + key contacts +
        rendered topology HTML. `generation` selects a saved snapshot id; empty/"current" → the
        live working copy. Always includes the list of generations for the picker."""
        from atlas.atp import generations
        g = generations.load_generation(customer, generation)
        return {"id": g["id"], "entries": g["entries"], "overview": g["overview"],
                "contacts": g["contacts"], "topology_html": g["topology_html"],
                "topology_uri": g.get("topology_uri", ""),
                "generations": generations.list_generations(customer)}

    def atp_generations(self, customer: str = "") -> list:
        """Saved ATP generations (timestamped snapshots), newest first, plus the live 'Current'."""
        from atlas.atp import generations
        return generations.list_generations(customer)

    def atp_save_overview(self, customer: str = "", overview: dict | None = None) -> dict:
        """Save a hand-edited Overview to the live/current working copy. Each paragraph the user
        changes is pinned (recorded in '_manual') so a later ✨ Generate won't overwrite it; the
        paragraphs they leave alone stay AI-refreshable."""
        from atlas.atp import profile_store
        keys = ("workloads_hosting", "applications_systems", "business_operations")
        prev = profile_store.load_overview(customer)
        prev_manual = set(prev.get("_manual") or [])
        ov = {k: (str((overview or {}).get(k) or "")).strip() for k in keys}
        manual = set(prev_manual)
        for k in keys:
            if ov[k] != (prev.get(k) or "").strip():   # user changed this paragraph -> pin it
                manual.add(k)
        ov["_manual"] = sorted(manual)
        profile_store.save_overview(customer, ov)
        return {"ok": True, "overview": ov}

    def atp_save_contacts(self, customer: str = "", contacts: list | None = None) -> dict:
        """Save a hand-edited Key Contacts list to the live/current working copy. Saved contacts are
        pinned (source='manual') so a later ✨ Generate keeps them and only adds brand-new people."""
        from atlas.atp import extract, profile_store
        cleaned = extract._clean_contacts(contacts or [], source="manual")
        profile_store.save_contacts(customer, cleaned)
        return {"ok": True, "count": len(cleaned), "contacts": cleaned}

    def continue_chat(self, id: str = "", text: str = "") -> dict:
        """Resume a saved chat artifact: drive a Chrome instance to its conversation URL,
        ask the follow-up, and append the reply to the same artifact."""
        from atlas.store import artifacts
        art = artifacts.get(id)
        if not art:
            return {"error": "chat not found"}
        url = art.get("chat_url") or ""
        if not url:
            return {"error": "this chat has no saved conversation URL"}
        jid = self.manager.submit("chat_continue",
                                  {"url": url, "prompt": text, "artifact_id": id},
                                  title=f"Chat · {text[:30]}", icon="💬")
        return {"job_id": jid}

    # ---- settings ----
    def get_settings(self) -> dict:
        from atlas.store import settings
        return settings.load()

    def save_settings(self, data: dict | None = None) -> dict:
        from atlas.store import settings
        return settings.save(data or {})

    # ---- Cron Jobs (scheduled instructions) ----
    def get_crons(self) -> list:
        """All scheduled crons, each with a human schedule label + next-run time (user's timezone)."""
        import datetime
        from atlas.store import cron, settings
        tzn = settings.load().get("timezone") or ""
        now = datetime.datetime.now()
        if tzn:
            try:
                from zoneinfo import ZoneInfo
                now = datetime.datetime.now(ZoneInfo(tzn))
            except Exception:
                pass
        out = []
        for e in cron.list_crons():
            nr = cron.next_run(e, now)
            disp = ""
            if nr:
                ap = "AM" if nr.hour < 12 else "PM"
                disp = f"{nr.strftime('%a %b %d')}, {((nr.hour - 1) % 12) + 1}:{nr.minute:02d} {ap}"
            out.append({**e, "label": cron.schedule_label(e), "next_run": disp})
        return out

    def todays_crons(self) -> list:
        """Enabled crons scheduled to run today (user's timezone), sorted by time — for the home
        page's 'today's schedule' list."""
        import datetime
        from atlas.store import cron, settings
        tzn = settings.load().get("timezone") or ""
        now = datetime.datetime.now()
        if tzn:
            try:
                from zoneinfo import ZoneInfo
                now = datetime.datetime.now(ZoneInfo(tzn))
            except Exception:
                pass
        today = now.date()
        out = []
        for e in cron.list_crons():
            if not e.get("enabled", True):
                continue
            rep = e.get("repeat", "daily")
            runs = (rep == "daily"
                    or (rep == "weekly" and today.weekday() in set(e.get("days") or []))
                    or (rep == "monthly" and today.day == e.get("dom", 1)))
            if not runs:
                continue
            out.append({"time": cron._fmt_time(e.get("time", "09:00")), "raw_time": e.get("time", ""),
                        "instruction": e.get("instruction", ""),
                        "fired": e.get("last_fired") == today.isoformat()})
        out.sort(key=lambda x: x["raw_time"])
        return out

    def add_cron(self, instruction: str = "", time: str = "09:00", repeat: str = "daily",
                 days: list | None = None, dom: int = 1, enabled: bool = True) -> dict:
        from atlas.store import cron
        if not (instruction or "").strip():
            return {"ok": False, "error": "instruction required"}
        e = cron.add_cron({"instruction": instruction, "time": time, "repeat": repeat,
                           "days": days or [], "dom": dom, "enabled": enabled})
        return {"ok": True, "cron": e}

    def update_cron(self, id: str = "", fields: dict | None = None) -> dict:
        from atlas.store import cron
        e = cron.update_cron(id, fields or {})
        return {"ok": bool(e), "cron": e}

    def toggle_cron(self, id: str = "") -> dict:
        from atlas.store import cron
        e = cron.toggle_cron(id)
        return {"ok": bool(e), "cron": e}

    def delete_cron(self, id: str = "") -> dict:
        from atlas.store import cron
        return {"ok": cron.delete_cron(id)}

    def get_brain_rules(self) -> dict:
        """The editable ATLAS Brain operating rules (the 'training' file)."""
        from atlas.brain import rules
        return {"text": rules.load_rules(), "path": str(rules.RULES_PATH)}

    def save_brain_rules(self, text: str = "") -> dict:
        from atlas.brain import rules
        return {"ok": True, "text": rules.save_rules(text)}

    def reset_brain_rules(self) -> dict:
        """Restore the brain rules to the built-in defaults, discarding any user edits."""
        from atlas.brain import rules
        return {"ok": True, "text": rules.save_rules(rules.DEFAULT_RULES)}

    def open_manual(self) -> dict:
        """Open the ATLAS User Guide PDF (project root) in the system default viewer."""
        import os
        import config
        p = config.PROJECT_ROOT / "ATLAS_User_Guide.pdf"
        if not p.exists():
            return {"ok": False, "error": "User Guide PDF not found in project root"}
        try:
            os.startfile(str(p))  # Windows: open in default PDF viewer
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def email_artifact(self, id: str = "", idx: int = 0) -> dict:
        """Open an Outlook draft for a trip-report artifact (recipient from Settings). Prefer the
        stable artifact id; fall back to a list index for older callers."""
        from atlas.integrations import outlook
        from atlas.store import artifacts, settings
        a = artifacts.get(id) if id else None
        if a is None:
            arts = artifacts.list_all()
            if idx < 0 or idx >= len(arts):
                return {"ok": False, "error": "artifact not found"}
            a = arts[idx]
        cfg = settings.load()
        sig = cfg.get("email_signature") or ""
        body = (a.get("text") or "")
        if sig:
            body += f"\n\n--\n{sig}"
        # Body text only — no .md attachment (the report is inline).
        return outlook.draft(
            to=cfg.get("trip_report_recipients", ""),
            subject=f"Trip Report — {a.get('title', '')}",
            body=body, attachment=None)

    # ---- misc ----
    def jslog(self, msg: str = "") -> bool:
        print(f"[js] {msg}", flush=True)
        return True

    def open_url(self, url: str) -> bool:
        import webbrowser
        webbrowser.open(url)
        return True

    def open_dashboard(self) -> bool:
        import webbrowser
        import config
        cards = load_for(_date_for("today")) or []
        html = dashboard_html.render(_greeting(), _today(), cards)
        p = config.RUNS_DIR / "dashboard.html"
        p.write_text(html, encoding="utf-8")
        webbrowser.open(p.as_uri())
        return True

    def shutdown(self) -> bool:
        try:
            get_pool().close_all()
        except Exception:
            pass
        return True
