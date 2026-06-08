"""Time reasoning helpers for the ATLAS brain — how a span of dates is validated and divided.

The brain (LLM classifier) resolves natural language like "May 21 to June 5" or "last two weeks"
into ABSOLUTE ISO dates (grounded on today's real date, since Copilot's own relative dates drift).
This module does only the deterministic part: validate those ISO dates, clamp a runaway span, list
the days, and chunk them into windows the job manager gathers in parallel — one Chrome instance per
window. No phrase parsing lives here.
"""
from __future__ import annotations

import datetime

MAX_SPAN_DAYS = 60   # safety: refuse to fan out across an absurd range


def parse_iso(s: str) -> datetime.date | None:
    """Lenient ISO date parse (accepts a full datetime too). Returns None on anything unparseable."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except Exception:
        return None


def clamp_range(start: str, end: str) -> tuple[datetime.date, datetime.date] | None:
    """Validate + normalize an ISO date range. Swaps if reversed, clamps the span to MAX_SPAN_DAYS
    (keeping `end`, walking `start` forward). Returns (start_date, end_date) or None if unparseable."""
    a, b = parse_iso(start), parse_iso(end)
    if a is None and b is None:
        return None
    if a is None:
        a = b
    if b is None:
        b = a
    if a > b:
        a, b = b, a
    if (b - a).days > MAX_SPAN_DAYS:
        a = b - datetime.timedelta(days=MAX_SPAN_DAYS)
    return a, b


def date_list(start: datetime.date, end: datetime.date) -> list[str]:
    """Every ISO date string from start..end inclusive."""
    n = (end - start).days
    return [(start + datetime.timedelta(days=i)).isoformat() for i in range(n + 1)]


def windows(dates: list[str], size: int = 5) -> list[list[str]]:
    """Chunk a list of ISO dates into windows of `size` (the unit of parallel gather)."""
    size = max(1, int(size or 1))
    return [dates[i:i + size] for i in range(0, len(dates), size)]
