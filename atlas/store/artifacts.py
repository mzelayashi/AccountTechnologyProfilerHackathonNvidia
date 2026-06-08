"""A running log of every artifact a skill produces (for the Artifacts browser)."""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

import config

_PATH = config.VAULT_DIR / "artifacts.json"
_seq = 0
# Serializes the load→mutate→save sequence in add/update/delete/backfill. The JobManager runs many
# pool-worker threads that write artifacts concurrently; without this they interleave and lose/tear
# records (which corrupted artifacts.json). _load/_save themselves do NOT take this lock (so the
# self-healing _save inside _load can't deadlock); only the public mutators below hold it.
_LOCK = threading.RLock()


def _new_id() -> str:
    global _seq
    _seq += 1
    return f"a{int(time.time() * 1000)}{_seq}"


def _salvage(raw: str) -> list:
    """Recover as many artifact records as possible from a corrupted artifacts.json. The corruption we
    hit is a (possibly short) valid leading JSON array followed by leftover 'extra data' from a torn /
    concurrent write. Strategy: decode the leading array, then brace-match every complete top-level
    {...} object in the remainder (string/escape aware), keep records that look like artifacts
    (id+skill+ts), de-dupe by id (first wins), sort by ts. Never raises."""
    recs: list = []
    # Brace-match complete objects across the WHOLE buffer (covers both a valid leading array's items
    # and any corrupted tail). Duplicates are removed afterwards by id.
    s = raw
    i, n = 0, len(s)
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        depth = 0
        instr = False
        esc = False
        start = i
        j = i
        while j < n:
            c = s[j]
            if instr:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    instr = False
            else:
                if c == '"':
                    instr = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            o = json.loads(s[start:j + 1])
                            if isinstance(o, dict) and o.get("id") and o.get("skill") and o.get("ts"):
                                recs.append(o)
                        except Exception:
                            pass
                        break
            j += 1
        i = j + 1
    # de-dupe by id (first occurrence wins), then order by timestamp
    seen, uniq = set(), []
    for r in recs:
        rid = r.get("id")
        if rid and rid not in seen:
            seen.add(rid)
            uniq.append(r)
    uniq.sort(key=lambda r: str(r.get("ts") or ""))
    return uniq


def _load() -> list:
    if not _PATH.exists():
        return []
    raw = _PATH.read_text(encoding="utf-8")
    try:
        recs = json.loads(raw)
        if not isinstance(recs, list):
            raise ValueError("artifacts.json is not a JSON array")
        for i, r in enumerate(recs):  # backfill ids for older records
            if not r.get("id"):
                r["id"] = f"a{r.get('ts', '')}-{i}"
        return recs
    except Exception as e:  # noqa: BLE001 — corrupted file: back up + recover, NEVER silently drop data
        recovered = _salvage(raw)
        try:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = _PATH.with_name(f"artifacts.json.corrupt-{stamp}")
            if not backup.exists():
                shutil.copy2(_PATH, backup)
            print(f"[artifacts] CORRUPT artifacts.json ({e}); backed up to {backup.name}; "
                  f"recovered {len(recovered)} record(s).", flush=True)
        except Exception:
            pass
        if recovered:
            _save(recovered)   # repair the file on first load so the corruption can't cascade
        return recovered


def _save(recs: list) -> None:
    """Atomic write: serialize to a temp file in the same dir, then os.replace() (atomic rename on
    Windows + POSIX). A torn or concurrent write can never leave a half-written artifacts.json."""
    data = json.dumps(recs, indent=2, ensure_ascii=False)
    tmp = _PATH.with_name(f"{_PATH.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, _PATH)


def add(skill_key: str, skill_name: str, icon: str, title: str, text: str,
        files: list[Path], diagram: str | None, data: dict | None = None,
        url: str | None = None) -> dict:
    rec = {
        "id": _new_id(),
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "skill": skill_key,
        "skill_name": skill_name,
        "icon": icon or "•",
        "title": title or skill_name,
        "text": text or "",
        "files": [{"name": p.name, "uri": p.as_uri()} for p in (files or [])],
        "diagram": diagram,
        "data": data if isinstance(data, dict) else None,
        "chat_url": url or "",
    }
    with _LOCK:
        recs = _load()
        recs.append(rec)
        _save(recs)
    return rec


def _ts_key(r: dict) -> str:
    ts = str(r.get("ts") or "")
    # A future-dated artifact (e.g. a backfilled report whose meeting date is in the future) isn't
    # actually "more recent" than now — keep it from topping Recent Artifacts.
    if ts[:10] > datetime.date.today().isoformat():
        return "0001-01-01" + ts          # sort to the very bottom (oldest)
    return ts


def list_all() -> list:
    """Full records, newest first by timestamp."""
    return sorted(_load(), key=_ts_key, reverse=True)


def summary(r: dict) -> dict:
    """Lightweight record for lists/search (no full text — just a short preview)."""
    text = r.get("text") or ""
    return {
        "id": r.get("id"), "ts": r.get("ts"), "skill": r.get("skill"),
        "skill_name": r.get("skill_name"), "icon": r.get("icon") or "•",
        "title": r.get("title"), "customer": r.get("customer") or "",
        "has_files": bool(r.get("files")), "has_diagram": bool(r.get("diagram")),
        "preview": " ".join(text.split())[:160],
    }


def list_summaries(limit: int | None = None, query: str = "") -> list:
    """Timestamp-sorted lightweight summaries — EXCLUDING brainwaves (they live in Brainwave
    History). With `query`, matches (case-insensitive) title + customer + skill_name + full text."""
    recs = sorted((r for r in _load() if r.get("skill") != "brainwave"), key=_ts_key, reverse=True)
    q = (query or "").strip().lower()
    if q:
        def hit(r):
            blob = " ".join(str(r.get(k) or "") for k in ("title", "customer", "skill_name", "text"))
            return q in blob.lower()
        recs = [r for r in recs if hit(r)]
    if limit:
        recs = recs[:limit]
    return [summary(r) for r in recs]


def list_brainwaves() -> list:
    """Brainwave artifacts only, newest first — for the Brainwave History view."""
    recs = sorted((r for r in _load() if r.get("skill") == "brainwave"), key=_ts_key, reverse=True)
    return [summary(r) for r in recs]


def get(art_id: str) -> dict | None:
    for r in _load():
        if r.get("id") == art_id:
            return r
    return None


def id_by_uri(uri: str) -> str | None:
    """The id of the artifact that owns a given file URI (links a folder file → its record)."""
    if not uri:
        return None
    return uri_id_map().get(uri)


def uri_id_map() -> dict:
    """{file_uri: artifact_id} for all artifacts — built in one pass (cheaper than per-file scans)."""
    m = {}
    for r in _load():
        for f in (r.get("files") or []):
            u = f.get("uri")
            if u and u not in m:
                m[u] = r.get("id")
    return m


def update(art_id: str, **patch) -> dict | None:
    """Merge fields into an existing artifact (e.g. append a chat turn). Returns the record."""
    with _LOCK:
        recs = _load()
        for r in recs:
            if r.get("id") == art_id:
                r.update(patch)
                _save(recs)
                return r
    return None


def _uri_to_path(uri: str) -> Path | None:
    if not uri or not uri.startswith("file:"):
        return None
    try:
        return Path(urllib.request.url2pathname(urllib.parse.urlparse(uri).path))
    except Exception:
        return None


def delete(art_id: str) -> dict:
    """Soft-delete an artifact: move its files (and diagram) into vault/recyclebin/artifacts/<id>/,
    drop it from the log so it vanishes from the frontend, and stash its record there for restore.
    Nothing is hard-deleted."""
    with _LOCK:
        recs = _load()
        rec = next((r for r in recs if r.get("id") == art_id), None)
        if not rec:
            return {"ok": False, "error": "artifact not found"}
        binroot = config.RECYCLEBIN_DIR / "artifacts" / art_id
        moved = 0
        targets = [f.get("uri") for f in (rec.get("files") or [])]
        if rec.get("diagram"):
            targets.append(rec["diagram"])
        for uri in targets:
            p = _uri_to_path(uri)
            if p and p.exists():
                binroot.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(p), str(binroot / p.name))
                    moved += 1
                except Exception:
                    pass
        _save([r for r in recs if r.get("id") != art_id])
    try:
        binroot.mkdir(parents=True, exist_ok=True)
        (binroot / "artifact.json").write_text(
            json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "id": art_id, "moved": moved}


_DATE_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _report_title(text: str, slug: str, customer: str) -> str:
    """Title for a trip-report artifact: prefer the MHT header line 'Trip Report | Topic | Cust'."""
    first = (text or "").lstrip().split("\n", 1)[0].strip()
    if first.lower().startswith("trip report") and "|" in first:
        parts = [p.strip() for p in first.split("|")]
        topic = parts[1] if len(parts) > 1 and parts[1] else ""
        if topic:
            return f"{customer} — {topic}" if customer else topic
    topic = re.sub(r"^\d{4}-\d{2}-\d{2}[_-]?", "", slug).replace("_", " ").strip()
    return f"{customer} — {topic}" if customer else (topic or slug)


def backfill_trip_reports() -> int:
    """Register every customer trip-report .md/.txt as an artifact so they're all readable in-app,
    searchable, and transferable. Idempotent — files already owned by an artifact are skipped."""
    from atlas.store import customers
    root = config.CUSTOMERS_DIR
    if not root.exists():
        return 0
    with _LOCK:
        recs = _load()
        known = {f.get("uri") for r in recs for f in (r.get("files") or [])}
        added = 0
        for cdir in sorted(root.iterdir()):
            if not cdir.is_dir():
                continue
            tr = cdir / "trip_reports"
            if not tr.exists():
                continue
            cust = customers._display_name(cdir)
            for p in sorted(tr.iterdir()):
                if p.suffix.lower() not in (".md", ".txt") or not p.is_file():
                    continue
                uri = p.as_uri()
                if uri in known:
                    continue
                try:
                    text = p.read_text(encoding="utf-8")
                except Exception:
                    continue
                m = _DATE_PREFIX.match(p.name)
                if m:
                    ts = f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00"
                else:
                    ts = datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
                recs.append({
                    "id": _new_id(),
                    "ts": ts,
                    "skill": "trip_report",
                    "skill_name": "Trip Report",
                    "icon": "🧾",
                    "title": _report_title(text, p.stem, cust)[:80],
                    "text": text,
                    "files": [{"name": p.name, "uri": uri}],
                    "diagram": None,
                    "data": None,
                    "chat_url": "",
                    "customer": cust,
                })
                known.add(uri)
                added += 1
        if added:
            _save(recs)
    return added
