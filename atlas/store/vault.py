"""Vault path helpers + per-account index (account.json)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import config


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_")
    return s or "Unknown"


def account_dir(name: str, create: bool = True) -> Path:
    d = config.ACCOUNTS_DIR / slug(name)
    if create:
        for sub in ("sources", "meetings", "briefings", "diagrams"):
            (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def load_account(name: str) -> dict:
    p = account_dir(name) / "account.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"name": name, "aliases": [], "domains": [], "stakeholders": [], "sources": []}


def save_account(name: str, data: dict) -> Path:
    p = account_dir(name) / "account.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def list_accounts() -> list[str]:
    if not config.ACCOUNTS_DIR.exists():
        return []
    return sorted(d.name for d in config.ACCOUNTS_DIR.iterdir() if d.is_dir())


def daily_dir(date_str: str, create: bool = True) -> Path:
    d = config.DAILY_DIR / date_str
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
