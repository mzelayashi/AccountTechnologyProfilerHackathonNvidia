"""User settings for ATLAS (the Settings page), persisted to vault/settings.json."""
from __future__ import annotations

import json

import config

_PATH = config.VAULT_DIR / "settings.json"

DEFAULTS = {
    "trip_report_recipients": "",   # comma/semicolon-separated emails the Email button pre-fills
    "email_signature": "",          # appended under the report body in the draft
    "auto_email_trip_reports": False,
    "system_pin": "",               # 6-digit PIN required to delete a customer (anti-accident guard)
    "guardrails_enabled": False,    # NeMo Guardrails input rail on the command box (off by default; fail-open)
    "guardrails_topical": True,     # rail: keep the brain on-topic (account intel + tech research)
    "guardrails_safety": True,      # rail: block unsafe / harmful requests
    "guardrails_injection": True,   # rail: block prompt-injection / jailbreak attempts
    "guardrails_strictness": "balanced",  # lenient | balanced | strict — how aggressively to refuse
    "guardrails_blocked_terms": "",   # comma-separated words/phrases refused outright in the command box
    "guardrails_blocked_domains": "",  # comma-separated domains the web-research agent must skip (e.g. reddit.com)
    "timezone": "America/New_York",  # IANA timezone the Cron Jobs scheduler fires in
    "show_chrome_windows": False,    # debug: launch the pool's Chrome on-screen (visible) instead of off-screen + minimized
    "gather_window_size": 5,         # days per parallel meeting-gather window (date-range trip-report jobs)
    "batch_concurrency": 4,          # max trip reports rendering at once in a fan-out (RAM throttle)
    "calendar_autorefresh_min": 30,  # auto re-gather yesterday/today/tomorrow every N min (0 = off)
    # --- Continual Suggestions (the proactive "next best action" panel) ---
    "continual_suggestions": True,   # master on/off for the suggestions panel
    "suggestions_ai": True,          # Tier-2 strategic (Copilot-Web) suggestions on/off
    "suggestions_frequency_min": 60, # min minutes between Tier-2 refreshes (30/60/120/240)
    "suggestions_focus_customer": "",# pin advice to ONE customer; "" = auto (follow the next meeting)
    "suggestions_workhours_only": True,  # only generate Tier-2 between ~7am–7pm
}


def load() -> dict:
    data = dict(DEFAULTS)
    if _PATH.exists():
        try:
            data.update(json.loads(_PATH.read_text(encoding="utf-8")) or {})
        except Exception:
            pass
    return data


def save(patch: dict) -> dict:
    data = load()
    for k in DEFAULTS:                 # only persist known keys
        if k in (patch or {}):
            data[k] = patch[k]
    _PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data
