"""The cron scheduler — a daemon that fires scheduled instructions through the Brain.

Runs while ATLAS is open. Every ~30s it checks each enabled cron against the current time in the
user's timezone (Settings) and fires anything due (once per occurrence). A fired cron submits a
`brain_route` job with its instruction — exactly as if the user typed it in the command box.
"""
from __future__ import annotations

import datetime
import threading
import time


def _now(tz_name: str) -> datetime.datetime:
    if tz_name:
        try:
            from zoneinfo import ZoneInfo
            return datetime.datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return datetime.datetime.now()                 # fall back to system local


def _due(e: dict, now: datetime.datetime) -> bool:
    if not e.get("enabled", True) or not (e.get("instruction") or "").strip():
        return False
    if e.get("last_fired") == now.date().isoformat():
        return False                               # already fired today
    try:
        h, m = (int(x) for x in e.get("time", "09:00").split(":"))
    except Exception:
        return False
    if (now.hour, now.minute) < (h, m):
        return False                               # not yet time today (same-day catch-up after)
    rep = e.get("repeat", "daily")
    if rep == "weekly" and now.weekday() not in set(e.get("days") or []):
        return False
    if rep == "monthly" and now.day != e.get("dom", 1):
        return False
    return True


def _tick() -> None:
    from atlas.jobs import get_manager
    from atlas.store import cron, settings
    tz = settings.load().get("timezone") or ""
    now = _now(tz)
    for e in cron.list_crons():
        try:
            if not _due(e, now):
                continue
            instr = e["instruction"].strip()
            get_manager().submit("brain_route", {"text": instr},
                                 title=f"⏰ {instr[:40]}", icon="⏰", mode="web")
            cron.mark_fired(e["id"], now.date().isoformat())
            print(f"[cron] fired '{instr[:60]}'", flush=True)
        except Exception as ex:  # noqa: BLE001 — one bad cron must not kill the loop
            print(f"[cron] error on {e.get('id')}: {ex}", flush=True)


def _loop() -> None:
    while True:
        try:
            _tick()
        except Exception as ex:  # noqa: BLE001
            print(f"[cron] tick error: {ex}", flush=True)
        time.sleep(30)


def start_scheduler() -> None:
    threading.Thread(target=_loop, daemon=True, name="atlas-cron").start()
    print("[cron] scheduler started", flush=True)


# --- calendar auto-refresh: re-gather the 3 days every N minutes (calendars change through the day) ---
def _refresh_three_days() -> None:
    from atlas.jobs import get_manager
    mgr = get_manager()
    today = datetime.date.today()
    for kind, off in (("yesterday", -1), ("today", 0), ("tomorrow", 1)):
        date = (today + datetime.timedelta(days=off)).isoformat()   # recomputed each cycle (rolls at midnight)
        mgr.submit("gather_day", {"date": date}, title=f"↻ Auto-refresh {kind}", icon="🗓")


def _calendar_loop() -> None:
    from atlas.store import settings
    while True:
        mins = 30
        try:
            mins = int(settings.load().get("calendar_autorefresh_min", 30) or 0)
        except Exception:
            mins = 30
        if mins <= 0:                       # disabled — re-check every 5 min so a later toggle takes effect
            time.sleep(300)
            continue
        time.sleep(mins * 60)               # sleep first (boot already did the initial gather)
        try:
            _refresh_three_days()
            print("[calendar] auto-refreshed yesterday/today/tomorrow", flush=True)
        except Exception as ex:  # noqa: BLE001 — never let a flaky cycle kill the loop
            print(f"[calendar] auto-refresh error: {ex}", flush=True)


def start_calendar_autorefresh() -> None:
    threading.Thread(target=_calendar_loop, daemon=True, name="atlas-calendar").start()
    print("[calendar] auto-refresh started", flush=True)
