"""People Resources — the SHI resource-alignment directory, CSV-backed.

The CSV at `config.PEOPLE_CSV` is the **permanent source of truth**: edits in the ATLAS UI write it,
and editing it on disk + hitting Refresh reloads it (a one-to-one mirror). The original
`resourcealignments.xlsx` is migrated once into the normalized CSV on first use; importing a new CSV
archives the old one (never destroys it).

The source spreadsheet is a 4-section directory (Engineers / Assessments / Tool Links / Vendor
contacts) with a messy embedded-header layout, so migration walks it section-by-section. The
`Specialty` column already holds the searchable skills (EDR/MDR, PAM, SASE…) and `Alignment` holds the
region (TOLA/Southeast, Cali/West/Healthcare…); internal vs external is derived from the email domain.
"""
from __future__ import annotations

import csv
import datetime
import re
import shutil
import unicodedata
from pathlib import Path

import config

# Normalized schema — one unified CSV across all categories.
COLUMNS = ["id", "category", "name", "location", "title", "practice", "specialty",
           "region", "manager", "email", "org", "link", "notes", "source"]

# ---- helpers ----------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")
_URL_RE = re.compile(r"https?://", re.I)
_DASH = re.compile(r"\s*-\s+")          # "Khang- Austin" / "Handel - Houston" (NOT "Hile-Hoffer")
_SECTION_TITLES = [("engineer resources", "Engineer"), ("assessment resources", "Assessment"),
                   ("tool links", "Tool"), ("vendor resources", "Vendor")]


def _clean(v) -> str:
    """Normalize a cell to clean text: kill the unicode replacement artifact, collapse whitespace."""
    if v is None:
        return ""
    s = str(v)
    if s.strip().lower() in ("nan", "none"):
        return ""
    s = unicodedata.normalize("NFKC", s).replace("�", " ")
    return re.sub(r"\s+", " ", s).strip()


def _email_in(*cells) -> str:
    for c in cells:
        m = _EMAIL_RE.search(c or "")
        if m:
            return m.group(0)
    return ""


def _org_from(email: str, category: str, name: str) -> str:
    """Internal (SHI) vs External, derived from the email domain; sensible default when no email."""
    if email:
        return "Internal" if email.lower().split("@")[-1] == "shi.com" else "External"
    if "internal" in (name or "").lower():
        return "Internal"
    return "External" if category == "Vendor" else "Internal"


def _split_suffix(name: str) -> tuple[str, str]:
    parts = _DASH.split(name, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return name, ""


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "x"


# ---- migration / normalization ---------------------------------------------

def _drop_blank_first_col(df):
    """The xlsx has a leading all-NaN spacer column; drop it if present so col 0 = SE."""
    import pandas as pd  # local — pandas only needed for migration/import
    if df.shape[1] and df.iloc[:, 0].isna().all():
        df = df.drop(columns=df.columns[0])
    df.columns = range(df.shape[1])
    return df


def _parse_sections(df, source_label: str) -> list[dict]:
    """Walk the 4-section alignment layout (a header=None dataframe, blank col already dropped) into
    normalized records. Tolerant of section-title rows, embedded header rows, and blank separators."""
    import pandas as pd  # noqa: F401
    records: list[dict] = []
    category = "Engineer"
    seq = 0
    for _, row in df.iterrows():
        cells = [_clean(row[c]) if c in row.index else "" for c in range(5)]
        se, practice, specialty, region, manager = (cells + ["", "", "", "", ""])[:5]
        if not any(cells):
            continue
        low = se.lower()
        # Section title row (only the first cell populated, names a section).
        hit = next((cat for key, cat in _SECTION_TITLES if key in low), None)
        if hit and not practice:
            category = hit
            continue
        if low.startswith("last updated"):
            continue
        # Embedded header row.
        if low in ("se", "resource") and practice.lower() in ("practice", "tool", "vendor", "specialty"):
            continue
        if not se:
            continue

        email = _email_in(se, specialty)
        link = specialty if _URL_RE.search(specialty) else ""
        # If Specialty is an email or URL it isn't a skill; otherwise it's the skills/description.
        spec = "" if (link or (specialty and _EMAIL_RE.fullmatch(specialty.strip()))) else specialty
        name, suffix = _split_suffix(se)
        location = suffix if category in ("Engineer", "Assessment") else ""
        title = suffix if category == "Vendor" else ""
        seq += 1
        records.append({
            "id": f"{seq:03d}-{_slug(name)[:24]}",
            "category": category,
            "name": name,
            "location": location,
            "title": title,
            "practice": practice,
            "specialty": spec,
            "region": "" if region.lower() == "alignment" else region,
            "manager": manager,
            "email": email,
            "org": _org_from(email, category, se),
            "link": link,
            "notes": "",
            "source": source_label,
        })
    return records


def _migrate_from_xlsx() -> list[dict]:
    """One-time: build resources.csv from resourcealignments.xlsx (kept in place)."""
    import pandas as pd
    xlsx = next(iter(sorted(config.PEOPLE_DIR.glob("*.xlsx"))), None)
    if not xlsx:
        return []
    df = _drop_blank_first_col(pd.read_excel(xlsx, header=None))
    # Capture the sheet's "Last Updated: m/d/yyyy" for provenance.
    stamp = ""
    for _, row in df.iterrows():
        c = _clean(row[0]) if 0 in row.index else ""
        if c.lower().startswith("last updated"):
            stamp = c.split(":", 1)[-1].strip()
            break
    records = _parse_sections(df, f"alignment {stamp}".strip())
    _write(records)
    return records


# ---- CSV read / write (the mirror) ------------------------------------------

def _write(records: list[dict]) -> None:
    config.PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
    with config.PEOPLE_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: (r.get(k) or "") for k in COLUMNS})


def load() -> list[dict]:
    """The resource list, read fresh from the CSV every call (so on-disk edits show after Refresh).
    Bootstraps from the xlsx on first use."""
    if not config.PEOPLE_CSV.exists():
        return _migrate_from_xlsx()
    out = []
    with config.PEOPLE_CSV.open("r", encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), 1):
            rec = {k: (row.get(k) or "").strip() for k in COLUMNS}
            if not rec["id"]:
                rec["id"] = f"{i:03d}-{_slug(rec['name'])[:24]}"
            out.append(rec)
    return out


def save_all(records: list[dict]) -> int:
    _write(records)
    return len(records)


def _next_id(records: list[dict], name: str) -> str:
    nums = [int(m.group(1)) for r in records if (m := re.match(r"(\d+)", r.get("id", "")))]
    return f"{(max(nums) + 1) if nums else 1:03d}-{_slug(name)[:24]}"


def add(record: dict) -> dict:
    records = load()
    rec = {k: (record.get(k) or "").strip() for k in COLUMNS}
    rec["category"] = rec["category"] or "Engineer"
    rec["org"] = rec["org"] or _org_from(rec["email"], rec["category"], rec["name"])
    rec["id"] = _next_id(records, rec["name"])
    records.append(rec)
    _write(records)
    return rec


def update(rid: str, patch: dict) -> dict | None:
    records = load()
    hit = None
    for r in records:
        if r.get("id") == rid:
            for k in COLUMNS:
                if k != "id" and k in patch:
                    r[k] = (patch.get(k) or "").strip()
            hit = r
            break
    if hit is None:
        return None
    _write(records)
    return hit


def delete(rid: str) -> bool:
    records = load()
    kept = [r for r in records if r.get("id") != rid]
    if len(kept) == len(records):
        return False
    _write(kept)
    return True


# ---- search (deterministic; powers both the UI filter and the brain skill) --

_STOP = {"a", "an", "the", "in", "that", "can", "do", "who", "need", "expert", "experts", "someone",
         "for", "with", "and", "or", "of", "to", "me", "i", "find", "resource", "region", "able",
         "does", "any", "is", "on", "my"}


def search(need: str = "", region: str = "", skill: str = "",
           practice: str = "", org: str = "", category: str = "") -> list[dict]:
    """Rank resources by keyword hits over name/specialty/region/practice/manager/title. A free-text
    `need` ("TOLA expert who can do PAM or EDR") is tokenized; region/specialty hits weigh more."""
    rows = load()
    toks = [t for t in re.split(r"[^a-z0-9/]+", (need or "").lower()) if len(t) >= 2 and t not in _STOP]
    out = []
    for r in rows:
        if category and r.get("category", "").lower() != category.lower():
            continue
        if org and r.get("org", "").lower() != org.lower():
            continue
        if practice and practice.lower() not in r.get("practice", "").lower():
            continue
        if region and region.lower() not in r.get("region", "").lower():
            continue
        if skill and skill.lower() not in r.get("specialty", "").lower():
            continue
        score = 0
        if toks:
            blob = " ".join(r.get(k, "") for k in
                            ("name", "specialty", "region", "practice", "manager", "title", "notes")).lower()
            spec, reg = r.get("specialty", "").lower(), r.get("region", "").lower()
            for t in toks:
                if t in blob:
                    score += 1
                if t in spec:
                    score += 2
                if t in reg:
                    score += 2
            if score == 0:
                continue
        out.append((score, r))
    out.sort(key=lambda x: -x[0])
    return [r for _, r in out]


# ---- import (archive the old, never destroy) --------------------------------

def _archive_current(tag: str) -> str | None:
    if not config.PEOPLE_CSV.exists():
        return None
    config.PEOPLE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = config.PEOPLE_ARCHIVE_DIR / f"{tag}__{stamp}.csv"
    i = 2
    while dest.exists():
        dest = config.PEOPLE_ARCHIVE_DIR / f"{tag}__{stamp}-{i}.csv"
        i += 1
    shutil.move(str(config.PEOPLE_CSV), str(dest))
    return str(dest)


def _load_foreign_csv(src: Path) -> list[dict]:
    """Read an imported CSV. If it already has our schema, use it directly; otherwise treat it as a
    raw alignment export and run the same section-normalization."""
    with src.open("r", encoding="utf-8-sig", newline="") as f:
        head = f.readline()
    if "specialty" in head.lower() and "region" in head.lower():
        with src.open("r", encoding="utf-8-sig", newline="") as f:
            return [{k: (row.get(k) or "").strip() for k in COLUMNS} for row in csv.DictReader(f)]
    import pandas as pd
    df = _drop_blank_first_col(pd.read_csv(src, header=None, dtype=str))
    return _parse_sections(df, f"import {datetime.date.today().isoformat()}")


def import_csv(src_path: str) -> dict:
    """Archive the current resources.csv, then load `src_path` as the new source of truth. The
    imported file is also moved into archive/ (provenance). Nothing is deleted."""
    src = Path(src_path)
    if not src.exists():
        return {"ok": False, "error": "file not found"}
    try:
        records = _load_foreign_csv(src)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"could not parse CSV: {e}"}
    if not records:
        return {"ok": False, "error": "no rows found in the imported CSV"}
    archived = _archive_current("resources")
    # assign ids if the foreign file lacked them
    for i, r in enumerate(records, 1):
        if not r.get("id"):
            r["id"] = f"{i:03d}-{_slug(r.get('name', ''))[:24]}"
    _write(records)
    try:                                   # keep the raw import for provenance too
        config.PEOPLE_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(config.PEOPLE_ARCHIVE_DIR /
                                  f"imported_{datetime.datetime.now():%Y%m%d-%H%M%S}_{src.name}"))
    except Exception:
        pass
    return {"ok": True, "count": len(records), "archived_old": archived}


def newest_import() -> str | None:
    """Most-recently-modified CSV staged in the import/ folder (for the in-app Import button)."""
    config.PEOPLE_IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    csvs = sorted(config.PEOPLE_IMPORT_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(csvs[0]) if csvs else None
