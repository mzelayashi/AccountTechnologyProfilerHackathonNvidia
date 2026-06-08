"""Per-customer technology inventory (the ATP 'data library'), stored as JSON in the customer's
account_technology_profile/ folder. Mirrors the key fields of the original ATP data_library.csv.
"""
from __future__ import annotations

import json

from atlas.store import customers

# The four editor categories (match the original ATP tool).
CATEGORIES = ("datacenter", "networking", "security", "edge_iot")

# Fields kept per technology entry (subset of the ATP 28-column schema that the GUI edits).
FIELDS = (
    "vendor", "product", "category", "model_number", "version", "specifications",
    "deployment_status", "deployment_percentage", "satisfaction_level", "notes",
    # Provenance: "trip_reports" entries are regenerated (replaced) on every ATP generate;
    # anything else (e.g. "" from the manual editor) is preserved across regenerations.
    "source",
    # Relevancy (computed deterministically by atp/recency.py from the trip reports).
    "mention_count", "first_seen", "last_seen", "last_seen_report",
)

DEPLOYMENT_STATUSES = ("active", "planned", "pilot", "evaluation", "legacy", "unknown")


def _path(customer: str):
    return customers.customer_dir(customer) / "account_technology_profile" / "data_library.json"


def load(customer: str) -> list[dict]:
    p = _path(customer)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else data.get("entries", [])
        except Exception:
            return []
    return []


def _clean(entry: dict) -> dict:
    out = {k: entry.get(k, "") for k in FIELDS}
    out["category"] = (out["category"] or "datacenter").lower()
    if out["category"] not in CATEGORIES:
        out["category"] = "datacenter"
    out["deployment_status"] = (out["deployment_status"] or "unknown").lower()
    if not isinstance(out["specifications"], dict):
        out["specifications"] = {}
    try:
        out["mention_count"] = int(out["mention_count"] or 0)
    except (TypeError, ValueError):
        out["mention_count"] = 0
    return out


def save(customer: str, entries: list[dict]) -> list[dict]:
    cleaned = [_clean(e) for e in (entries or []) if (e.get("vendor") or "").strip()]
    p = _path(customer)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
    return cleaned
