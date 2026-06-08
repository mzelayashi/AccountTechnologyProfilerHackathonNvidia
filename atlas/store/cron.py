"""Cron Jobs — scheduled ATLAS instructions, persisted to vault/cron.json.

Each entry is an instruction (free text, run through the Brain when it fires) plus a schedule. The
scheduler daemon (atlas/jobs/scheduler.py) reads these and fires them in the user's timezone.
"""
from __future__ import annotations

import datetime
import json
import time

import config

_PATH = config.CRON_PATH
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]   # 0..6, Python weekday()


def _load() -> list:
    if _PATH.exists():
        try:
            d = json.loads(_PATH.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
        except Exception:
            return []
    return []


def _save(rows: list) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    _PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def _clean(e: dict) -> dict:
    """Normalize/validate one entry."""
    repeat = e.get("repeat") if e.get("repeat") in ("daily", "weekly", "monthly") else "daily"
    t = str(e.get("time") or "09:00")
    try:
        h, m = (int(x) for x in t.split(":")[:2])
        t = f"{max(0, min(23, h)):02d}:{max(0, min(59, m)):02d}"
    except Exception:
        t = "09:00"
    days = [int(d) for d in (e.get("days") or []) if str(d).isdigit() and 0 <= int(d) <= 6]
    try:
        dom = max(1, min(31, int(e.get("dom") or 1)))
    except Exception:
        dom = 1
    return {
        "id": e.get("id") or f"c{int(time.time() * 1000)}",
        "instruction": (e.get("instruction") or "").strip(),
        "time": t,
        "repeat": repeat,
        "days": sorted(set(days)) or ([datetime.date.today().weekday()] if repeat == "weekly" else []),
        "dom": dom,
        "enabled": bool(e.get("enabled", True)),
        "created": e.get("created") or datetime.datetime.now().isoformat(timespec="seconds"),
        "last_fired": e.get("last_fired") or "",
    }


def list_crons() -> list:
    return _load()


def add_cron(fields: dict) -> dict:
    rows = _load()
    e = _clean(fields or {})
    rows.append(e)
    _save(rows)
    return e


def update_cron(cron_id: str, fields: dict) -> dict | None:
    rows = _load()
    for i, r in enumerate(rows):
        if r.get("id") == cron_id:
            merged = {**r, **(fields or {}), "id": cron_id}
            rows[i] = _clean(merged)
            _save(rows)
            return rows[i]
    return None


def delete_cron(cron_id: str) -> bool:
    rows = _load()
    new = [r for r in rows if r.get("id") != cron_id]
    if len(new) != len(rows):
        _save(new)
        return True
    return False


def toggle_cron(cron_id: str) -> dict | None:
    rows = _load()
    for r in rows:
        if r.get("id") == cron_id:
            r["enabled"] = not r.get("enabled", True)
            _save(rows)
            return r
    return None


def mark_fired(cron_id: str, date_iso: str) -> None:
    rows = _load()
    for r in rows:
        if r.get("id") == cron_id:
            r["last_fired"] = date_iso
            _save(rows)
            return


# ---- human-readable schedule + next run (for the UI) -------------------------------------------
def _fmt_time(hhmm: str) -> str:
    try:
        h, m = (int(x) for x in hhmm.split(":"))
        ap = "AM" if h < 12 else "PM"
        return f"{((h - 1) % 12) + 1}:{m:02d} {ap}"
    except Exception:
        return hhmm


def schedule_label(e: dict) -> str:
    t = _fmt_time(e.get("time", "09:00"))
    rep = e.get("repeat", "daily")
    if rep == "weekly":
        days = ", ".join(_WEEKDAYS[d] for d in sorted(e.get("days") or [])) or "—"
        return f"Weekly · {days} at {t}"
    if rep == "monthly":
        dom = e.get("dom", 1)
        suf = "th" if 11 <= dom % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(dom % 10, "th")
        return f"Monthly · {dom}{suf} at {t}"
    return f"Daily at {t}"


def next_run(e: dict, now: datetime.datetime) -> datetime.datetime | None:
    """Next datetime this cron would fire at/after `now` (tz-aware now in)."""
    if not e.get("enabled", True):
        return None
    try:
        h, m = (int(x) for x in e.get("time", "09:00").split(":"))
    except Exception:
        return None
    rep, days, dom = e.get("repeat"), set(e.get("days") or []), e.get("dom", 1)
    for add in range(0, 366):
        d = (now + datetime.timedelta(days=add))
        cand = d.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand < now:
            continue
        if rep == "weekly" and cand.weekday() not in days:
            continue
        if rep == "monthly" and cand.day != dom:
            continue
        return cand
    return None
