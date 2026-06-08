"""Render the daily briefing as a rich, dark 'Jarvis/Palantir' HTML dashboard.

Designed for full fidelity in a real browser/WebView and to degrade gracefully in
tkinterweb. Meeting cards link via the custom scheme `atlas:meeting:<index>`.
"""
from __future__ import annotations

import html
import re

_TIME = re.compile(r"Time:\s*([0-9]{1,2}:[0-9]{2}\s*[APMapm]{0,2})")
_ORG = re.compile(r"Organizer:\s*(.+)")


def _start_hour(body: str) -> int:
    m = _TIME.search(body)
    if not m:
        return 99
    t = m.group(1).upper().replace(" ", "")
    mm = re.match(r"(\d{1,2}):(\d{2})(AM|PM)?", t)
    if not mm:
        return 99
    h = int(mm.group(1)) % 12
    if mm.group(3) == "PM":
        h += 12
    return h


def _kind(title: str) -> tuple[str, str]:
    t = title.lower()
    if "admin" in t or "focus" in t:
        return "🗂", "admin"
    if "demo" in t:
        return "🖥", "demo"
    if "intro" in t or "discovery" in t:
        return "🤝", "intro"
    if "review" in t or "win wire" in t or "ahod" in t:
        return "📊", "review"
    if "internal" in t or "sync" in t:
        return "🔁", "internal"
    return "📌", "default"


def _accent(kind: str) -> str:
    return {
        "admin": "#6e7681", "demo": "#a371f7", "intro": "#39d353",
        "review": "#f0b429", "internal": "#56d4dd", "default": "#58a6ff",
    }.get(kind, "#58a6ff")


def _bucket(h: int) -> str:
    if h < 11:
        return "Morning"
    if h < 12:
        return "Late Morning"
    if h < 14:
        return "Midday"
    return "Afternoon"


def _meta(body: str) -> tuple[str, str, str]:
    tm = _TIME.search(body)
    org = _ORG.search(body)
    # preview: first meaningful prep line
    preview = ""
    for line in body.splitlines():
        s = line.strip()
        if s and not s.lower().startswith(("time:", "organizer:", "prep:")) and "&#124;" not in s:
            preview = s
            if s.lower().startswith(("context", "expected", "your role", "how to")):
                preview = s
                break
    return (tm.group(1) if tm else ""), (org.group(1).strip() if org else ""), preview[:160]


def _to_minutes(time_s: str):
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*([APap][Mm])?", time_s or "")
    if not m:
        return None
    h = int(m.group(1)) % 12
    if (m.group(3) or "").lower() == "pm":
        h += 12
    return h * 60 + int(m.group(2))


def enrich(meetings: list[dict], day_kind: str = "today") -> list[dict]:
    """Structured, sorted meeting items for the dashboard.

    `past` (→ Recap + Create Trip Report) is true for ALL of yesterday's meetings, for
    today's meetings whose start time has already elapsed, and never for tomorrow's.
    `day_kind` is "yesterday" | "today" | "tomorrow".
    """
    import datetime

    now_min = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute
    items = []
    for i, m in enumerate(meetings):
        body = m.get("body", "")
        hour = _start_hour(body)
        icon, kind = _kind(m.get("title", ""))
        time_s, org, preview = _meta(body)
        sm = _to_minutes(time_s)
        if day_kind == "yesterday":
            past = True
        elif day_kind == "tomorrow":
            past = False
        else:
            past = bool(sm is not None and sm < now_min)
        items.append({
            "i": i, "title": m.get("title", ""), "body": body,
            "hour": hour if hour < 99 else 50, "icon": icon, "kind": kind,
            "accent": _accent(kind), "time": time_s, "org": org, "preview": preview,
            "conflict": ("⚠" in body or "conflict" in body.lower()), "bucket": _bucket(hour),
            "past": past,
        })
    items.sort(key=lambda x: x["hour"])
    return items


def render(greeting: str, date_str: str, meetings: list[dict]) -> str:
    # enrich + sort
    items = []
    for i, m in enumerate(meetings):
        body = m.get("body", "")
        hour = _start_hour(body)
        icon, kind = _kind(m.get("title", ""))
        time_s, org, preview = _meta(body)
        conflict = "⚠️" in body or "conflict" in body.lower()
        items.append({"i": i, "title": m.get("title", ""), "hour": hour, "icon": icon,
                      "kind": kind, "accent": _accent(kind), "time": time_s, "org": org,
                      "preview": preview, "conflict": conflict})
    items.sort(key=lambda x: x["hour"])

    # group
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(_bucket(it["hour"]), []).append(it)

    cards_html = []
    for bucket in ("Morning", "Late Morning", "Midday", "Afternoon"):
        if bucket not in groups:
            continue
        cards_html.append(f'<div class="bucket"><div class="bucket-h">{bucket}</div><div class="grid">')
        for it in groups[bucket]:
            badge = '<span class="conflict">⚠ conflict</span>' if it["conflict"] else ""
            cards_html.append(f"""
            <a class="card" style="--a:{it['accent']}" href="atlas:meeting:{it['i']}">
              <div class="row"><span class="icon">{it['icon']}</span>
                <span class="time">{html.escape(it['time'])}</span>{badge}</div>
              <div class="title">{html.escape(it['title'])}</div>
              <div class="org">{html.escape(it['org'])}</div>
              <div class="prev">{html.escape(it['preview'])}</div>
            </a>""")
        cards_html.append("</div></div>")

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
:root{{color-scheme:dark}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#13233b 0%,#0b0f17 55%,#080b11 100%);
 color:#e6edf3;font-family:'Segoe UI',Arial,sans-serif}}
.top{{padding:26px 30px 8px}}
.brand{{color:#56d4dd;font-weight:700;letter-spacing:3px;font-size:13px}}
.greet{{font-size:30px;font-weight:800;margin:6px 0 0}}
.date{{color:#7fd1e0;font-size:15px;margin-top:2px}}
.count{{color:#8b949e;font-size:12px;margin-top:10px}}
.bucket{{padding:8px 30px 4px}}
.bucket-h{{color:#8b949e;font-size:12px;text-transform:uppercase;letter-spacing:2px;
 border-bottom:1px solid #20283400;margin:14px 0 10px;
 background:linear-gradient(90deg,#1b2433,transparent);padding:6px 10px;border-left:3px solid #2b3a52}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.card{{display:block;text-decoration:none;color:inherit;background:#0f1620;border:1px solid #1d2735;
 border-left:4px solid var(--a);border-radius:12px;padding:14px 16px;transition:.15s;
 box-shadow:0 1px 0 #00000040}}
.card:hover{{border-color:var(--a);box-shadow:0 0 22px -6px var(--a);transform:translateY(-2px)}}
.row{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.icon{{font-size:20px;filter:drop-shadow(0 0 6px var(--a))}}
.time{{color:var(--a);font-weight:700;font-size:13px}}
.conflict{{margin-left:auto;color:#f85149;font-size:11px;border:1px solid #5a2a2a;
 border-radius:20px;padding:2px 8px;background:#2a1414}}
.title{{font-weight:700;font-size:15px;line-height:1.25}}
.org{{color:#8b949e;font-size:12px;margin:3px 0 8px}}
.prev{{color:#9fb0c3;font-size:12px;line-height:1.4;max-height:54px;overflow:hidden}}
</style></head><body>
<div class="top"><div class="brand">◆ SHI ATLAS</div>
<div class="greet">{html.escape(greeting)}</div>
<div class="date">{html.escape(date_str)}</div>
<div class="count">{len(items)} meetings today · click a card for full prep</div></div>
{''.join(cards_html)}
<div style="height:30px"></div></body></html>"""
