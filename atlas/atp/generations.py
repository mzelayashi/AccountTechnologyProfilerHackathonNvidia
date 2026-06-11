"""Versioned ATP generations — every '✨ Generate from trip reports' run is archived as an
immutable, timestamped snapshot so the user can compare how a customer's profile drifts over time.

Layout (per customer):
    account_technology_profile/
        data_library.json / overview.json / contacts.json / topology.html   <- live "current"
        generations/<YYYYMMDD-HHMMSS>/
            data_library.json / overview.json / contacts.json / topology.html / meta.json

The flat files stay the editable working copy (the Technology Profile editor edits those); the
snapshots are read-only. The customer page lists snapshots newest-first and shows the selected
one's Overview, Key Contacts, and Topology.
"""
from __future__ import annotations

import datetime
import json

from atlas.atp import data_library, profile_store, topology_html
from atlas.store import customers


def _gens_dir(customer: str):
    return customers.customer_dir(customer) / "account_technology_profile" / "generations"


def _read_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except Exception:
        return default


def snapshot(customer: str, entries: list, overview: dict, contacts: list) -> dict:
    """Archive the just-generated profile as a new timestamped snapshot; returns its meta."""
    now = datetime.datetime.now()
    gid = now.strftime("%Y%m%d-%H%M%S")
    # %-d/%-I aren't portable (fail on Windows strftime), so build the display string by hand.
    display = (f"{now.strftime('%b')} {now.day}, {now.year} · "
               f"{((now.hour - 1) % 12) + 1}:{now.minute:02d} {'AM' if now.hour < 12 else 'PM'}")
    meta = {
        "id": gid,
        "created_iso": now.isoformat(timespec="seconds"),
        "created_display": display,
        "techs": len(entries or []),
        "contacts": len(contacts or []),
        "has_overview": bool(overview),
    }
    d = _gens_dir(customer) / gid
    d.mkdir(parents=True, exist_ok=True)
    (d / "data_library.json").write_text(
        json.dumps(entries or [], indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "overview.json").write_text(
        json.dumps(overview or {}, indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "contacts.json").write_text(
        json.dumps(contacts or [], indent=2, ensure_ascii=False), encoding="utf-8")
    (d / "topology.html").write_text(
        topology_html.render(customer, entries or []), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def _current_meta(customer: str) -> dict | None:
    """Synthesize a 'Current' pseudo-generation from the live flat files (for customers generated
    before versioning existed, or whose latest edits live only in the working copy)."""
    entries = data_library.load(customer)
    overview = profile_store.load_overview(customer)
    contacts = profile_store.load_contacts(customer)
    if not (entries or overview or contacts):
        return None
    return {"id": "current", "created_iso": "", "created_display": "Current (live)",
            "techs": len(entries), "contacts": len(contacts), "has_overview": bool(overview)}


def list_generations(customer: str) -> list[dict]:
    """All snapshots newest-first. Always prepends the live 'Current' entry so the editable working
    copy is selectable too; falls back to just 'Current' when no snapshots exist yet."""
    gens = []
    gd = _gens_dir(customer)
    if gd.exists():
        for sub in gd.iterdir():
            if sub.is_dir():
                m = _read_json(sub / "meta.json", None)
                if isinstance(m, dict) and m.get("id"):
                    gens.append(m)
    gens.sort(key=lambda m: m.get("id", ""), reverse=True)
    cur = _current_meta(customer)
    return ([cur] if cur else []) + gens


def delete_generation(customer: str, gen_id: str) -> dict:
    """Soft-delete one snapshot: move its folder into vault/recyclebin/generations/ (nothing erased —
    it just vanishes from the generations picker, exactly like deleting a customer). The live 'Current'
    profile is the editable working copy and is NOT deletable here."""
    import shutil
    import config
    from atlas.store import vault
    if not gen_id or gen_id == "current":
        return {"ok": False, "error": "The live Current profile can't be deleted."}
    d = _gens_dir(customer) / gen_id
    if not d.exists():
        return {"ok": False, "error": "generation not found"}
    dest = config.RECYCLEBIN_DIR / "generations" / f"{vault.slug(customer)}__{gen_id}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    i = 2
    while dest.exists():
        dest = dest.with_name(f"{vault.slug(customer)}__{gen_id}-{i}")
        i += 1
    try:
        shutil.move(str(d), str(dest))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not move generation: {e}"}
    return {"ok": True, "id": gen_id, "recycled_to": str(dest)}


def load_generation(customer: str, gen_id: str = "") -> dict:
    """Return a generation's {entries, overview, contacts, topology_html}. '' or 'current' →
    the live flat files; otherwise the snapshot folder. Renders topology HTML on read."""
    if gen_id and gen_id != "current":
        d = _gens_dir(customer) / gen_id
        if d.exists():
            entries = _read_json(d / "data_library.json", [])
            overview = _read_json(d / "overview.json", {})
            contacts = _read_json(d / "contacts.json", [])
            topo = d / "topology.html"
            html = topo.read_text(encoding="utf-8") if topo.exists() \
                else topology_html.render(customer, entries)
            return {"id": gen_id, "entries": entries, "overview": overview, "contacts": contacts,
                    "topology_html": html, "topology_uri": topo.as_uri() if topo.exists() else ""}
    # current / fallback: live flat files
    entries = data_library.load(customer)
    live_topo = customers.customer_dir(customer) / "account_technology_profile" / "topology.html"
    return {"id": "current", "entries": entries,
            "overview": profile_store.load_overview(customer),
            "contacts": profile_store.load_contacts(customer),
            "topology_html": topology_html.render(customer, entries),
            "topology_uri": live_topo.as_uri() if live_topo.exists() else ""}
