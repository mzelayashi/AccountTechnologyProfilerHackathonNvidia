"""Persistence for the customer Overview (3 business paragraphs) and Key Contacts, stored in the
customer's account_technology_profile/ folder alongside data_library.json."""
from __future__ import annotations

import json

from atlas.store import customers


def _p(customer: str, name: str):
    return customers.customer_dir(customer) / "account_technology_profile" / name


def load_overview(customer: str) -> dict:
    p = _p(customer, "overview.json")
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")) or {}
        except Exception:
            return {}
    return {}


def save_overview(customer: str, data: dict) -> None:
    p = _p(customer, "overview.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data or {}, indent=2, ensure_ascii=False), encoding="utf-8")


def load_contacts(customer: str) -> list:
    p = _p(customer, "contacts.json")
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return d if isinstance(d, list) else []
        except Exception:
            return []
    return []


def save_contacts(customer: str, data: list) -> None:
    p = _p(customer, "contacts.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data or [], indent=2, ensure_ascii=False), encoding="utf-8")
