"""ONE-TIME migration: split the old OneNoteTR/trips.mht archive (already parsed into
.parsed_trips_cache.json) into individual markdown trip reports, filed by customer into the
ATLAS vault, in the original ATP/MHT format. Consolidates customer-name variants.

Run:  python -m atlas.atp.migrate           # dry run — prints the consolidation report
      python -m atlas.atp.migrate --write   # actually write the files
"""
from __future__ import annotations

import datetime
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from atlas.store import customers, vault

# Freshly parsed from the CURRENT OneNoteTR/trips.mht (see parse_trips.py) — NOT the stale cache.
CACHE = Path(r"C:\hackathonsandbox\cache\fresh_trips.json")

# Section headers (from the old config.py) — used to find where the body starts and to keep
# headers on their own line during reflow.
_HEADERS = [
    "summary", "agenda", "opportunities identified & bantc", "opportunities identified",
    "opps identified & bantc", "opps identified", "opportunities discovered", "opportunities",
    "bantc", "initiatives", "tech profile updates", "environment", "meeting notes",
    "detailed discussion", "technical notes", "roles", "potential next steps", "next steps",
    "security", "endpoint", "infrastructure", "infra",
]

# Explicit consolidation for abbreviations/families/typos in THIS trips.mht that fuzzy alone misses.
_ALIASES = {
    "uhcu": "United Heritage Credit Union", "shi + uhcu": "United Heritage Credit Union",
    "united heritage credit union (uhcu)": "United Heritage Credit Union",
    "shi + united heritage credit union": "United Heritage Credit Union",
    "gpb": "Great Plains Bank", "great plains national bank": "Great Plains Bank",
    "great plaines": "Great Plains Bank", "great plains": "Great Plains Bank",
    "mccu": "MCCU", "members choice credit union (mccu)": "MCCU", "members choice credit union": "MCCU",
    "southern bank corp": "Southern Bancorp",
    "getix": "GetixHealth", "getix health": "GetixHealth", "gettix": "GetixHealth",
    "gettixhealth": "GetixHealth", "shi + getixhealth": "GetixHealth",
    "wardlaw": "Wardlaw Claims", "argo": "Argo Data", "argo data resources": "Argo Data",
    "shi + argo data": "Argo Data", "pilot thomas logistics": "Pilot Thomas", "ptl": "Pilot Thomas",
    "otto": "Otto Aviation", "spark": "Spark Energy", "ranger": "Ranger Energy",
    "cavender auto": "Cavender", "interlink": "Interlinc", "interlimc": "Interlinc",
    "amerivet": "AmeriVet", "claro enterprises": "Claro", "claro enterprise": "Claro",
    "claro enterprise solutions": "Claro", "claro telvista": "Claro",
    "helixesg": "Helix", "helix energy": "Helix", "helix energy solutions group": "Helix",
    "outdoor cap co": "Outdoor Cap", "outdoor cap company": "Outdoor Cap",
    "smartstart": "Smart Start", "alert360": "Alert 360", "esco": "ESCO",
    "pro petro": "Pro Petro", "propetro": "Pro Petro", "al copeland": "Al Copelands",
    "pinnery": "Pinnergy", "ezeefiber": "Ezee Fiber", "ezee fiber": "Ezee Fiber",
    "bistow": "Bristow", "bristow group": "Bristow", "global shop solutions": "Global Shop",
    "shi + global shop solutions": "Global Shop", "aws": "AWS Inc",
}


def _clean_name(name: str) -> str:
    """Collapse whitespace/newlines and drop a trailing parenthetical, e.g. 'HW\\n Resources' ->
    'HW Resources', 'United Heritage Credit Union (UHCU)' -> 'United Heritage Credit Union'."""
    s = " ".join((name or "").split())
    s = re.sub(r"\s*\([^)]*\)\s*$", "", s).strip()
    return s


def _norm(name: str) -> str:
    s = _clean_name(name).lower()
    s = re.sub(r"\b(inc|llc|corp|ltd|co|company|group|holdings|health|healthcare)\.?\b", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def consolidate(names_counts: dict) -> dict:
    """Map each raw customer name -> canonical name."""
    raw_to_canon = {}
    # 1) explicit aliases
    for raw in names_counts:
        key = _clean_name(raw).lower()
        if key in _ALIASES:
            raw_to_canon[raw] = _ALIASES[key]

    # 2) cluster the rest by normalized key + fuzzy
    clusters: list[list[str]] = []
    norms: list[str] = []
    for raw in sorted(names_counts, key=lambda n: -names_counts[n]):
        if raw in raw_to_canon:
            continue
        n = _norm(raw)
        placed = False
        for i, cn in enumerate(norms):
            if n == cn or difflib.SequenceMatcher(None, n, cn).ratio() >= 0.9:
                clusters[i].append(raw)
                placed = True
                break
        if not placed:
            clusters.append([raw])
            norms.append(n)

    for cl in clusters:
        # canonical = most reports, then longest, prefer a multi-word real name
        canon = sorted(cl, key=lambda r: (names_counts[r], len(r), " " in r))[-1]
        for raw in cl:
            raw_to_canon[raw] = canon
    return raw_to_canon


def _fmt_date(meta: dict):
    iso = meta.get("meeting_date")
    if iso:
        try:
            dt = datetime.datetime.fromisoformat(iso)
            return dt.strftime("%m/%d/%Y"), dt.strftime("%Y-%m-%d"), False
        except Exception:
            pass
    return "2026", "2026-00-00", True   # undated -> year only; flag


def _is_header(line: str) -> bool:
    low = line.lower().rstrip(":").strip()
    low = re.sub(r"\s*\(.*\)$", "", low)  # drop "(High-Level)" etc.
    return len(line) <= 45 and any(low == h or low.startswith(h + " ") or low == h for h in _HEADERS) \
        or (len(line) <= 45 and low in _HEADERS)


def _is_bullet(line: str) -> bool:
    return bool(re.match(r"^\s*([•\-\*–—]|\d+[.)]|opportunity\s*\d+|[BANTC]\s*[–:\-]\s)", line, re.I))


def _strip_to_body(full_text: str) -> str:
    """Drop the CRM link + Customer/AE/Topic/District/Meeting Date box + the internal-notes line —
    everything above the real content. Body = after '*Internal notes…externally*', else from the
    first section header, else after the 'Meeting Date' line."""
    m = re.search(r"\*\s*internal notes.*?externally\s*\*", full_text, re.I | re.S)
    if m:
        return full_text[m.end():].lstrip("\n")
    lines = full_text.split("\n")
    for i, ln in enumerate(lines):
        if _is_header(ln.strip()):
            return "\n".join(lines[i:])
    m2 = re.search(r"meeting date.*?\n", full_text, re.I)
    return full_text[m2.end():] if m2 else full_text


def _reflow(full_text: str) -> str:
    lines = _strip_to_body(full_text).split("\n")
    out: list[str] = []
    para: list[str] = []

    def flush():
        if para:
            out.append(" ".join(para).strip())
            para.clear()

    for raw in lines:
        ln = raw.strip()
        if not ln:
            flush()
            if out and out[-1] != "":
                out.append("")
            continue
        if _is_header(ln):
            flush()
            if out and out[-1] != "":
                out.append("")
            out.append(ln.rstrip(":").strip())
            out.append("")
            continue
        if _is_bullet(ln):
            flush()
            out.append(ln)
            continue
        para.append(ln)
    flush()
    # collapse 3+ blank lines
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _build(report: dict, customer: str) -> tuple[str, str]:
    m = report["metadata"]
    topic = " ".join((m.get("topic") or "Meeting").split()) or "Meeting"
    ae = " ".join((m.get("ae_name") or "").split())
    disp_date, file_date, _undated = _fmt_date(m)
    body = _reflow(report.get("full_text") or "")
    content = (
        f"Trip Report | {topic} | {customer}\n\n"
        f"Customer: {customer}\n"
        f"AE: {ae}\n"
        f"Topic: {topic}\n"
        f"Meeting Date {disp_date}\n\n"
        f"*Internal notes – Please read and edit before sending externally*\n\n"
        f"{body}\n"
    )
    fname = f"{file_date}_{vault.slug(topic)[:50]}.md"
    return content, fname


def _cust_of(report: dict) -> str:
    c = _clean_name(report["metadata"].get("customer_name") or "")
    return c if c else "_Unsorted"


def run(write: bool = False) -> dict:
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    reports = data["reports"]
    counts = Counter(_cust_of(r) for r in reports)
    canon = consolidate(dict(counts))

    by_canon = defaultdict(list)       # canonical -> raw variants
    for raw in counts:
        by_canon[canon.get(raw, raw)].append(raw)

    written = 0
    undated = 0
    per_customer = Counter()
    used = defaultdict(set)   # cust -> filenames already written (avoid collisions)
    for r in reports:
        raw = _cust_of(r)
        cust = canon.get(raw, raw)
        per_customer[cust] += 1
        _d, _fd, und = _fmt_date(r["metadata"])
        undated += 1 if und else 0
        if write:
            content, fname = _build(r, cust)
            base, cand, n = fname[:-3], fname, 2
            while cand in used[cust]:        # same date+topic → suffix so no report is lost
                cand = f"{base}-{n}.md"
                n += 1
            used[cust].add(cand)
            dest = customers.customer_dir(cust) / "trip_reports" / cand
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            written += 1

    # migration report
    lines = [f"# Trip Report Migration — {len(reports)} reports → {len(by_canon)} customers",
             f"_{'WRITTEN' if write else 'DRY RUN'} · {undated} undated (dated 2026)_", ""]
    for cust in sorted(by_canon, key=lambda c: -per_customer[c]):
        variants = sorted(set(by_canon[cust]))
        extra = [v for v in variants if v != cust]
        merged = f"  ⇐ {', '.join(extra)}" if extra else ""
        lines.append(f"- **{cust}** — {per_customer[cust]} report(s){merged}")
    report_md = "\n".join(lines)
    if write:
        (customers.config.CUSTOMERS_DIR / "_migration_report.md").write_text(report_md, encoding="utf-8")

    return {"reports": len(reports), "customers": len(by_canon), "written": written,
            "undated": undated, "report_md": report_md}


if __name__ == "__main__":
    res = run(write="--write" in sys.argv)
    print(res["report_md"].encode("ascii", "replace").decode())
    print(f"\n{res['reports']} reports · {res['customers']} customers · "
          f"written={res['written']} · undated={res['undated']}")
