"""Customer Vault — per-customer folders mirrored on disk (the ATP repository root).

Each customer is a folder under vault/customers/<slug>/ with four fixed subfolders. Artifacts
created elsewhere in ATLAS can be 'assigned' to a customer, which physically moves the file in.
"""
from __future__ import annotations

import datetime
import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

import config
from atlas.store import artifacts, vault

SUBFOLDERS = ("artifacts", "account_technology_profile", "network_diagrams", "trip_reports")


def customer_dir(name: str, create: bool = True) -> Path:
    d = config.CUSTOMERS_DIR / vault.slug(name)
    if create:
        for sub in SUBFOLDERS:
            (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _meta_path(name: str) -> Path:
    return customer_dir(name) / "customer.json"


def create_customer(name: str) -> dict:
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}
    d = customer_dir(name)                       # makes the tree
    mp = d / "customer.json"
    if not mp.exists():
        mp.write_text(json.dumps(
            {"name": name, "created": datetime.datetime.now().isoformat(timespec="seconds")},
            indent=2, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "name": name, "slug": vault.slug(name)}


def delete_customer(name: str) -> dict:
    """Soft-delete: move the customer's whole folder into vault/recyclebin/ (nothing is actually
    erased — the user purges the recycle bin by hand). It vanishes from the ATLAS frontend because
    list_customers only scans CUSTOMERS_DIR."""
    d = customer_dir(name, create=False)
    if not d.exists():
        return {"ok": False, "error": "customer not found"}
    config.RECYCLEBIN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.RECYCLEBIN_DIR / f"{d.name}__{stamp}"
    i = 2
    while dest.exists():
        dest = config.RECYCLEBIN_DIR / f"{d.name}__{stamp}-{i}"
        i += 1
    try:
        shutil.move(str(d), str(dest))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not move folder: {e}"}
    return {"ok": True, "name": name, "recycled_to": str(dest)}


def _display_name(d: Path) -> str:
    mp = d / "customer.json"
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8")).get("name") or d.name
        except Exception:
            pass
    return d.name


def _files(d: Path) -> list[dict]:
    if not d.exists():
        return []
    return [{"name": p.name, "uri": p.as_uri()}
            for p in sorted(d.iterdir()) if p.is_file() and p.name != "customer.json"]


def list_customers() -> list[dict]:
    root = config.CUSTOMERS_DIR
    out = []
    if root.exists():
        for d in sorted(root.iterdir()):
            if not d.is_dir():
                continue
            counts = {sub: len(_files(d / sub)) for sub in SUBFOLDERS}
            out.append({"name": _display_name(d), "slug": d.name, "counts": counts,
                        "total": sum(counts.values())})
    return out


def detail(name: str) -> dict:
    d = customer_dir(name, create=False)
    folders = {sub: _files(d / sub) for sub in SUBFOLDERS}
    # Link each trip-report file to its artifact so the UI can open the in-app readable view.
    umap = artifacts.uri_id_map()
    for f in folders.get("trip_reports", []):
        aid = umap.get(f.get("uri", ""))
        if aid:
            f["artifact_id"] = aid
    return {
        "name": _display_name(d) if d.exists() else name,
        "slug": vault.slug(name),
        "path": str(d),
        "folders": folders,
    }


def _uri_to_path(uri: str) -> Path | None:
    if not uri or not uri.startswith("file:"):
        return None
    try:
        return Path(urllib.request.url2pathname(urllib.parse.urlparse(uri).path))
    except Exception:
        return None


def _subfolder_for(skill_key: str) -> str:
    k = (skill_key or "").lower()
    if "trip_report" in k:
        return "trip_reports"
    if "topology" in k or "environment" in k or "diagram" in k:
        return "network_diagrams"
    return "artifacts"


def assign_artifact(artifact_id: str, name: str) -> dict:
    """Move an artifact's files into the customer's folder (by type), filing its text as .md
    if it has no files, and tag the artifact with the customer."""
    art = artifacts.get(artifact_id)
    if not art:
        return {"ok": False, "error": "artifact not found"}
    cdir = customer_dir(name)
    sub = _subfolder_for(art.get("skill", ""))
    dest = cdir / sub
    dest.mkdir(parents=True, exist_ok=True)

    new_files = []
    moved = 0
    for f in (art.get("files") or []):
        src = _uri_to_path(f.get("uri", ""))
        if src and src.exists():
            target = dest / src.name
            try:
                shutil.move(str(src), str(target))
                moved += 1
                new_files.append({"name": target.name, "uri": target.as_uri()})
                continue
            except Exception:
                pass
        new_files.append(f)  # keep original ref if move failed

    # No real file but has text → file the text as a markdown copy.
    if not new_files and (art.get("text") or "").strip():
        safe = vault.slug(art.get("title") or art.get("skill_name") or "artifact")[:60]
        p = dest / f"{safe}.md"
        p.write_text(art.get("text", ""), encoding="utf-8")
        moved += 1
        new_files = [{"name": p.name, "uri": p.as_uri()}]

    artifacts.update(artifact_id, customer=name, files=new_files)
    return {"ok": True, "customer": name, "moved": moved, "folder": sub}
