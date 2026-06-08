"""Deterministic relevancy for each technology — how many trip reports mention it and the most
recent one — computed by scanning the customer's trip reports (no AI counting). Reproduces the
original SHI Account Technology Profiler's `_assign_source_dates`: word-boundary match of the
vendor/product name against each report's text; `mention_count` = number of matching reports,
`last_seen` = the newest matching report's date.
"""
from __future__ import annotations

import datetime
import re

from atlas.store import customers

_DATE_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_MEETING_DATE = re.compile(r"Meeting Date\s+(\d{1,2})/(\d{1,2})/(\d{4})", re.I)


def _label(slug: str, d: datetime.date | None) -> str:
    # %-d is not portable (fails on Windows strftime); build the date part by hand.
    topic = slug.replace("_", " ").strip() or "Trip report"
    if not d:
        return topic
    return f"{topic} · {d.strftime('%b')} {d.day}, {d.year}"


def report_index(customer: str) -> list[tuple[datetime.date | None, str, str]]:
    """(date, label, lowercased_text) for each trip report. Date from the YYYY-MM-DD filename
    prefix, falling back to a 'Meeting Date MM/DD/YYYY' header line."""
    d = customers.customer_dir(customer, create=False) / "trip_reports"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.glob("*")):
        if p.suffix.lower() not in (".md", ".txt"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        date = None
        slug = p.stem
        m = _DATE_PREFIX.match(p.name)
        if m:
            try:
                date = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                date = None
            slug = re.sub(r"^\d{4}-\d{2}-\d{2}[_-]?", "", p.stem)
        if date is None:
            mm = _MEETING_DATE.search(text)
            if mm:
                try:
                    date = datetime.date(int(mm.group(3)), int(mm.group(1)), int(mm.group(2)))
                except ValueError:
                    date = None
        out.append((date, _label(slug, date), text.lower()))
    return out


def _terms(entry: dict) -> list[str]:
    """Search terms for an entry: its product (if distinctive) and its vendor."""
    terms = []
    product = (entry.get("product") or "").strip()
    vendor = (entry.get("vendor") or "").strip()
    if len(product) >= 3:
        terms.append(product)
    if vendor and vendor.lower() not in (t.lower() for t in terms):
        terms.append(vendor)
    return terms


def assign(customer: str, entries: list[dict]) -> list[dict]:
    """Set mention_count / first_seen / last_seen / last_seen_report on each entry in place."""
    index = report_index(customer)
    for e in entries or []:
        patterns = [re.compile(r"\b" + re.escape(t.lower()) + r"\b") for t in _terms(e)]
        matches = []  # (date, label)
        for date, label, text in index:
            if any(p.search(text) for p in patterns):
                matches.append((date, label))
        e["mention_count"] = len(matches)
        dated = [(d, lab) for d, lab in matches if d is not None]
        if dated:
            dated.sort(key=lambda x: x[0])
            e["first_seen"] = dated[0][0].isoformat()
            e["last_seen"] = dated[-1][0].isoformat()
            e["last_seen_report"] = dated[-1][1]
        elif matches:                       # matched, but no parseable date
            e["first_seen"] = ""
            e["last_seen"] = ""
            e["last_seen_report"] = matches[-1][1]
        else:
            e["first_seen"] = e["last_seen"] = e["last_seen_report"] = ""
    return entries
